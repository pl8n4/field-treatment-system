from __future__ import annotations

from datetime import date, timedelta
from operator import add
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver

# Import to resolve a langgraph serialization issue
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.constants import END, START
from langgraph.graph import StateGraph, add_messages
from langgraph.types import Command, interrupt

from data_layer.records import (
    applications_for,
    find_field,
    find_product,
)
from data_layer.retriever import search
from data_layer.schemas import (
    Application,
    FarmField,
    LabelChunk,
    ProductLimits,
    TraitPackage,
    WeatherForecast,
    stage_position,
)
from data_layer.weather import WeatherUnavailable, get_forecast
from workflow.config import (
    GEMINI_MODEL,
    MODEL_MAX_TOKENS,
    MODEL_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    validate_settings,
)
from workflow.schemas import (
    CriticDecision,
    IntakeDecision,
    RuleCheck,
    RuleEngineResult,
    TreatmentPlan,
    TreatmentRequest,
    WorkOrderResult,
)

MAX_REVISIONS = 1
MAX_CONVERSATION_MESSAGES = 12

# One query per restriction the rule engine checks. Retrieval is deterministic:
# no LLM rewrites these, and each is filtered to the proposed product's label.
EVIDENCE_QUERIES = (
    "maximum application rate per acre and maximum per season",
    "growth stage application timing window",
    "wind speed restriction and downwind spray drift buffer",
    "air temperature restriction and temperature inversion",
    "restricted entry interval and pre-harvest interval",
)


def _stage_in_window(stage: str, product: ProductLimits) -> bool:
    """
    Whether a growth stage falls inside a label's application window. Compared by
    season position, never as strings. An unrecognised stage returns False.
    """
    position = stage_position(stage)
    if position is None:
        return False

    earliest = product.earliest_growth_stage
    latest = product.latest_growth_stage
    latest_exclusive = product.latest_growth_stage_exclusive

    if earliest and (bound := stage_position(earliest)) is not None:
        if position < bound:
            return False

    if latest and (bound := stage_position(latest)) is not None:
        if position > bound:
            return False

    if latest_exclusive and (bound := stage_position(latest_exclusive)) is not None:
        if position >= bound:
            return False

    return True


def _stage_window_describe(product: ProductLimits) -> str:
    """The label's application window in words, for a rule explanation."""
    earliest = product.earliest_growth_stage or "any"
    if product.latest_growth_stage_exclusive:
        return (
            f"{earliest} up to but not including "
            f"{product.latest_growth_stage_exclusive}"
        )
    return f"{earliest} to {product.latest_growth_stage or 'any'}"


INTAKE_PROMPT = ChatPromptTemplate.from_template("""
You are the intake parser for an agricultural field-treatment
review workflow.

Extract the request and determine whether the workflow can continue.

The user must supply:

- field_id
- observed_issue
- proposed_product
- proposed_date

The application may fill these fields from internal records or label
evidence:

- crop
- acres
- requested_rate

Choose exactly one next step:

- clarify:
  One or more user-required fields are missing.

- gather_context:
  All user-required fields are present. Other information may be
  retrieved from application records.

Rules:

- Use the full conversation.
- Combine follow-up answers with earlier messages.
- Do not invent missing information.
- Resolve relative dates using the supplied current date.
- Format proposed_date as YYYY-MM-DD.
- Return every field required by the output schema.
- Do not recommend or approve a treatment.

CURRENT DATE:

{current_date}

CONVERSATION:

{conversation}
    """.strip())

SPECIALIST_PROMPT = ChatPromptTemplate.from_template("""
You are the agricultural treatment-plan specialist.

Draft a proposed treatment plan using only the supplied request,
farm records, weather, application history, and retrieved label
evidence.

Requirements:

- Never claim the plan is approved.
- Always require qualified human review.
- Do not invent unsupported label requirements.
- Cite the supplied evidence sources.
- Use the rate in request.requested_rate. Context gathering fills this
  with the product default when the user does not supply a rate.
- Use the acreage in request.acres. Context gathering fills this with
  the field acreage when the user does not supply an acreage.
- Do not replace either resolved value unless previous review feedback
  explicitly requires a correction.
- Keep request.proposed_date. Weather is not something you can plan
  around: moving the spray to a calmer day is the grower's call, not
  yours, and the plan must stay on the day that was asked for so the
  reviewer sees the real conflict.
- Address every previous critic revision instruction.

REQUEST:
{request}

FIELD RECORD:
{field}

PRODUCT RECORD:
{product}

APPLICATION HISTORY:
{history}

WEATHER:
{weather}

LABEL EVIDENCE:
{evidence}

PREVIOUS REVIEW:
{previous_review}
    """.strip())

CRITIC_PROMPT = ChatPromptTemplate.from_template("""
You are the compliance critic for an agricultural field-treatment
review workflow.

Review the proposed plan, deterministic rule checks, and retrieved
evidence.

Return exactly one verdict:

- clean:
  All required checks passed and the plan may proceed to human review.

- fixable:
  A correctable problem exists and the Specialist should revise.

- insufficient_info:
  Required information or supporting evidence is unavailable.

- hard_violation:
  A non-correctable compliance violation exists.

Rules:

- A failed hard-violation rule requires hard_violation.
- A failed fixable rule requires fixable unless a hard violation exists.
- Missing relevant evidence requires insufficient_info.
- Never approve an actual field treatment.
- Explain the result using visible business reasoning.
- Cite supplied sources where relevant.

PLAN:
{plan}

RULE CHECKS:
{rule_checks}

EVIDENCE:
{evidence}
    """.strip())


class AgriculturalState(TypedDict, total=False):
    """Shared data that moves through the LangGraph workflow."""

    # Current user input and parsed request
    question: str
    request: TreatmentRequest
    intake: IntakeDecision

    # Gathered operational context
    field_record: FarmField
    product_record: ProductLimits
    application_history: list[Application]
    weather: WeatherForecast

    # Retrieved knowledge
    evidence: list[LabelChunk]
    context_sources: list[str]

    # Specialist and critic output
    plan: TreatmentPlan
    rule_result: RuleEngineResult
    review: CriticDecision

    # Controlled revision loop
    revision_count: int
    max_revisions: int

    # Human decision and simulated action
    human_decision: Literal["approved", "rejected"]
    work_order: WorkOrderResult

    # Workflow outcome
    final_status: str
    final_message: str
    error: str | None
    missing_information: list[str]

    # Append-only state
    audit_log: Annotated[list[str], add]
    messages: Annotated[list[AnyMessage], add_messages]

    # Conversation tracking
    turn_number: int

    # Thread tracking
    thread_id: str


class AgriculturalWorkflow:
    """
    Coordinates the agricultural field-treatment review process.
    """

    def __init__(self) -> None:
        validate_settings()

        self.llm = self._build_chat_model()

        self.intake_chain = self._build_structured_chain(
            INTAKE_PROMPT,
            IntakeDecision,
        )

        self.specialist_chain = self._build_structured_chain(
            SPECIALIST_PROMPT,
            TreatmentPlan,
        )

        self.critic_chain = self._build_structured_chain(
            CRITIC_PROMPT,
            CriticDecision,
        )

        serializer = JsonPlusSerializer(
            allowed_msgpack_modules=[
                TreatmentRequest,
                IntakeDecision,
                FarmField,
                ProductLimits,
                # nested inside FarmField and ProductLimits, so the checkpointer
                # needs it by name to restore state after a human-review pause
                TraitPackage,
                Application,
                WeatherForecast,
                LabelChunk,
                TreatmentPlan,
                RuleCheck,
                RuleEngineResult,
                CriticDecision,
                WorkOrderResult,
            ]
        )

        self.checkpointer = InMemorySaver(
            serde=serializer,
        )

        self.graph = self._build_graph()

    @staticmethod
    def _build_chat_model():
        if MODEL_PROVIDER == "ollama":
            return ChatOllama(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                temperature=0,
                num_predict=MODEL_MAX_TOKENS,
            )

        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            max_tokens=MODEL_MAX_TOKENS,
            temperature=0,
            max_retries=2,
        )

    def _build_structured_chain(self, prompt, schema):
        structured_model = self.llm.with_structured_output(
            schema,
            method="json_schema",
        )

        base_chain = prompt | structured_model

        return base_chain.with_retry(
            retry_if_exception_type=(Exception,),
            stop_after_attempt=3,
            wait_exponential_jitter=True,
        )

    def _build_graph(self):
        builder = StateGraph(AgriculturalState)

        builder.add_node("intake", self._intake_node)
        builder.add_node("clarify", self._clarify_node)
        builder.add_node("gather_context", self._gather_context_node)
        builder.add_node("retrieve", self._retrieve_node)
        builder.add_node("specialist", self._specialist_node)
        builder.add_node("refresh_weather", self._refresh_weather_node)
        builder.add_node("rules", self._rule_engine_node)
        builder.add_node("critic", self._critic_node)
        builder.add_node("human_review", self._human_review_node)
        builder.add_node("write_work_order", self._work_order_node)
        builder.add_node("rejected", self._rejected_node)
        builder.add_node("escalate", self._escalation_node)
        builder.add_node("failure", self._failure_node)

        builder.add_edge(
            START,
            "intake",
        )

        builder.add_conditional_edges(
            "intake",
            self._route_after_intake,
            {
                "clarify": "clarify",
                "gather_context": "gather_context",
                "failure": "failure",
            },
        )

        builder.add_conditional_edges(
            "gather_context",
            self._route_after_context,
            {
                "retrieve": "retrieve",
                "clarify": "clarify",
                "failure": "failure",
            },
        )

        builder.add_conditional_edges(
            "retrieve",
            self._route_after_retrieval,
            {
                "specialist": "specialist",
                "clarify": "clarify",
                "failure": "failure",
            },
        )

        builder.add_conditional_edges(
            "specialist",
            self._route_after_specialist,
            {
                "refresh_weather": "refresh_weather",
                "failure": "failure",
            },
        )

        builder.add_edge(
            "refresh_weather",
            "rules",
        )

        builder.add_conditional_edges(
            "rules",
            self._route_after_rules,
            {
                "critic": "critic",
                "failure": "failure",
            },
        )

        builder.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {
                "human_review": "human_review",
                "specialist": "specialist",
                "clarify": "clarify",
                "escalate": "escalate",
                "failure": "failure",
            },
        )

        builder.add_conditional_edges(
            "human_review",
            self._route_after_human_review,
            {
                "write_work_order": "write_work_order",
                "rejected": "rejected",
            },
        )

        for terminal_node in [
            "clarify",
            "write_work_order",
            "rejected",
            "escalate",
            "failure",
        ]:
            builder.add_edge(
                terminal_node,
                END,
            )

        return builder.compile(
            checkpointer=self.checkpointer,
        )

    @staticmethod
    def _content_to_text(content) -> str:
        """
        Convert LangChain message content into readable text.
        """

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []

            for block in content:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(str(block["text"]))
                else:
                    text_parts.append(str(block))

            return " ".join(text_parts)

        return str(content)

    def _format_conversation(
        self,
        state: AgriculturalState,
    ) -> str:
        """
        Format recent messages for the triage prompt.
        """

        lines: list[str] = []

        messages = state.get(
            "messages",
            [],
        )[-MAX_CONVERSATION_MESSAGES:]

        for message in messages:
            if isinstance(message, HumanMessage):
                role = "User"
            else:
                role = "Assistant"

            content = self._content_to_text(message.content)
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _intake_node(
        self,
        state: AgriculturalState,
    ) -> dict:
        """
        Validate, normalize, extract, classify, and route the treatment request.
        """

        try:
            question = state["question"].strip()

            if not question:
                raise ValueError("The request cannot be empty")

            intake = self.intake_chain.invoke(
                {
                    "current_date": date.today().isoformat(),
                    "conversation": self._format_conversation(state),
                }
            )

            request = intake.request

            required_fields = {
                "field_id": request.field_id,
                "observed_issue": request.observed_issue,
                "proposed_product": request.proposed_product,
                "proposed_date": request.proposed_date,
            }

            missing_information = [
                field_name
                for field_name, value in required_fields.items()
                if (value is None or (isinstance(value, str) and not value.strip()))
            ]

            selected_route = "clarify" if missing_information else "gather_context"

            if missing_information:
                routing_explanation = (
                    "Missing user-required fields: "
                    + ", ".join(missing_information)
                    + "."
                )
            else:
                routing_explanation = (
                    "All user-required fields are present. "
                    "Crop, acres, and requested rate may be loaded "
                    "from system records or product evidence."
                )

            return {
                "question": question,
                "intake": intake,
                "request": request,
                "error": None,
                "missing_information": missing_information,
                "turn_number": state.get("turn_number", 0) + 1,
                "audit_log": [
                    (
                        "Intake selected the "
                        f"{selected_route} route: "
                        f"{routing_explanation}"
                    )
                ],
            }

        except Exception as exc:
            return {
                "error": f"Intake failed: {exc}",
                "audit_log": ["Intake failed."],
            }

    @staticmethod
    def _clarify_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Stop and request missing information from the user.
        """

        missing = state.get(
            "missing_information",
            [],
        )

        if not missing and state.get("review"):
            missing = state["review"].issues

        missing = list(dict.fromkeys(missing))

        message = "Additional information is required: " + ", ".join(
            missing or ["unspecified information"]
        )

        return {
            "final_status": "needs_information",
            "final_message": message,
            "messages": [
                AIMessage(content=message),
            ],
            "audit_log": ["Workflow paused for user information."],
        }

    @staticmethod
    def _gather_context_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Load the field, product limits, spray history, and forecast that the
        specialist and the rule engine reason over.

        A lookup that cannot be resolved is reported as missing information
        rather than an error: find_field and find_product return None both when
        nothing matches and when the text matches more than one record, and
        either way the answer is to ask the user which one they meant.
        """

        try:
            request = state["request"]

            proposed_date = (
                date.fromisoformat(request.proposed_date)
                if request.proposed_date
                else date.today()
            )

            missing: list[str] = []

            field = find_field(request.field_id or "")
            if field is None:
                missing.append(
                    f"A field matching {request.field_id or '(none given)'!r} — "
                    "no field has that name or id, or the text matches several."
                )

            product = find_product(request.proposed_product or "")
            if product is None:
                missing.append(
                    f"A product matching "
                    f"{request.proposed_product or '(none given)'!r} — "
                    "no label has that name, or the text matches several."
                )

            if missing:
                return {
                    "missing_information": missing,
                    "audit_log": [
                        "Context lookup could not resolve the field or product."
                    ],
                }

            # Assertions for mypy. The above return returns if these are not true
            assert field is not None
            assert product is not None

            if request.acres is not None and request.acres > field.acres:
                return {
                    "missing_information": [
                        (
                            f"Requested acreage is {request.acres}, but "
                            f"{field.name} contains {field.acres} acres."
                        )
                    ],
                    "audit_log": [
                        "Requested acreage exceeded the resolved field acreage."
                    ],
                }

            effective_acres = (
                request.acres if request.acres is not None else field.acres
            )

            effective_rate = (
                request.requested_rate
                if request.requested_rate is not None
                else product.default_rate_fl_oz_per_acre
            )

            if effective_rate is None:
                return {
                    "missing_information": [f"An application rate for {product.name}"],
                    "audit_log": [
                        "No requested or default application rate was available."
                    ],
                }

            resolved_request = request.model_copy(
                update={
                    "crop": request.crop or field.crop,
                    "acres": effective_acres,
                    "requested_rate": effective_rate,
                }
            )

            history = applications_for(
                field.id,
                season_year=proposed_date.year,
            )

            try:
                weather = get_forecast(
                    field.latitude,
                    field.longitude,
                    proposed_date,
                )
            except WeatherUnavailable as exc:
                return {
                    "request": resolved_request,
                    "missing_information": [
                        f"A forecast for {proposed_date}: {exc}",
                    ],
                    "audit_log": [
                        f"Weather unavailable for {proposed_date}.",
                    ],
                }

            return {
                "request": resolved_request,
                "field_record": field,
                "product_record": product,
                "application_history": history,
                "weather": weather,
                "error": None,
                "audit_log": [
                    (
                        f"Loaded {field.name} ({field.id}, {field.trait_package.value}, "
                        f"{field.growth_stage}), {product.name}, "
                        f"{len(history)} prior application(s) in {proposed_date.year}, "
                        f"and the {proposed_date} forecast."
                    )
                ],
            }

        except Exception as exc:
            return {
                "error": f"Context gathering failed: {exc}",
                "audit_log": ["Context gathering failed."],
            }

    def _retrieve_node(
        self,
        state: AgriculturalState,
    ) -> dict:
        """
        Pull label text for the proposed product out of the Chroma store.

        One query per restriction the rule engine checks, so the specialist has
        something to cite for each. Filtered to this label and to the crop in the
        ground — a turf rate cited for soybean reads as plausible as the truth.
        """

        try:
            product = state["product_record"]
            field = state["field_record"]
            request = state["request"]

            queries = list(EVIDENCE_QUERIES)
            if request.observed_issue:
                queries.insert(0, f"control of {request.observed_issue}")

            evidence: list[LabelChunk] = []
            seen: set[tuple[str, int, str]] = set()

            for query in queries:
                for chunk in search(query, product=product.name, crop=field.crop, k=2):
                    key = (chunk.epa_reg_no, chunk.page, chunk.text[:80])
                    if key in seen:
                        continue
                    seen.add(key)
                    evidence.append(chunk)

            sources = sorted({chunk.source for chunk in evidence})

            return {
                "evidence": evidence,
                "context_sources": sources,
                "missing_information": (
                    [] if evidence else [f"Label evidence for {product.name}"]
                ),
                "error": None,
                "audit_log": [
                    (
                        f"Retrieved {len(evidence)} label chunks for {product.name} "
                        f"scoped to {field.crop} from {len(sources)} source(s) "
                        f"over {len(queries)} queries."
                    )
                ],
            }

        except Exception as exc:
            return {
                "error": f"Retrieval failed: {exc}",
                "audit_log": ["Retrieval failed."],
            }

    @staticmethod
    def _refresh_weather_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Re-fetch the forecast when the plan lands on a day the current one does
        not cover.

        Context gathering fetches for the requested date. A plan that moves to
        another day would otherwise be checked against the old day's wind, so a
        date change could neither clear a wind violation nor cause one. On
        failure the stale forecast is left in place and the rule engine fails
        the wind checks closed rather than reading it.
        """

        plan = state.get("plan")
        weather = state.get("weather")

        if not plan or not weather or weather.target_date == plan.treatment_date:
            return {}

        field = state["field_record"]

        try:
            refreshed = get_forecast(
                field.latitude,
                field.longitude,
                plan.treatment_date,
            )
        except WeatherUnavailable as exc:
            return {
                "audit_log": [
                    (
                        f"No forecast for the planned {plan.treatment_date}: "
                        f"{exc}. Wind checks cannot be made against "
                        f"{weather.target_date}'s forecast."
                    )
                ],
            }

        return {
            "weather": refreshed,
            "audit_log": [
                (
                    f"Re-fetched the forecast for the planned "
                    f"{plan.treatment_date} (the request asked for "
                    f"{weather.target_date})."
                )
            ],
        }

    def _specialist_node(
        self,
        state: AgriculturalState,
    ) -> dict:
        try:
            previous_review = state.get("review")

            history_text = "\n".join(
                record.model_dump_json() for record in state["application_history"]
            )

            evidence_text = "\n\n".join(
                chunk.model_dump_json() for chunk in state["evidence"]
            )

            plan = self.specialist_chain.invoke(
                {
                    "request": state["request"].model_dump_json(indent=2),
                    "field": state["field_record"].model_dump_json(indent=2),
                    "product": state["product_record"].model_dump_json(indent=2),
                    "history": history_text,
                    "weather": state["weather"].model_dump_json(indent=2),
                    "evidence": evidence_text,
                    "previous_review": (
                        previous_review.model_dump_json(indent=2)
                        if previous_review
                        else "No previous review."
                    ),
                }
            )

            return {
                "plan": plan,
                "error": None,
                "audit_log": [
                    (
                        "Specialist drafted treatment plan "
                        f"revision {state.get('revision_count', 0)}."
                    )
                ],
            }

        except Exception as exc:
            return {
                "error": f"Specialist failed: {exc}",
                "audit_log": ["Specialist failed."],
            }

    @staticmethod
    def _rule_engine_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Deterministic compliance checks. No LLM is involved.

        Every limit on ProductLimits is optional, where None means the label
        sets no such restriction. Those are recorded as informational passes
        rather than dropped, so the trace shows the rule was considered.
        """

        try:
            request = state["request"]
            plan = state["plan"]
            product = state["product_record"]
            field = state["field_record"]
            weather = state["weather"]

            def rule(rule_name, limit, passed, severity, explanation):
                """One check. `passed` and `explanation` are deferred so they
                are never evaluated against a None limit."""
                if limit is None:
                    return RuleCheck(
                        rule_name=rule_name,
                        passed=True,
                        severity="informational",
                        explanation="The label sets no such restriction.",
                    )

                return RuleCheck(
                    rule_name=rule_name,
                    passed=passed(),
                    severity=severity,
                    explanation=explanation(),
                )

            expected_treatment_date = (
                date.fromisoformat(request.proposed_date)
                if request.proposed_date
                else None
            )

            # The forecast is fetched for the date that was asked for. If the
            # plan moved to another day, it describes different weather than
            # the one being checked, and a wind rule read against it would pass
            # or fail a day nobody looked at.
            forecast_covers_plan = weather.target_date == plan.treatment_date

            def weather_rule(rule_name, limit, passed, severity, explanation):
                """A rule that reads the forecast. Fails closed when the
                forecast is for a different day than the plan.
                """
                if limit is None or forecast_covers_plan:
                    return rule(rule_name, limit, passed, severity, explanation)

                return RuleCheck(
                    rule_name=rule_name,
                    passed=False,
                    severity=severity,
                    explanation=(
                        f"The plan is for {plan.treatment_date} but the only "
                        f"forecast on hand is for {weather.target_date}, so "
                        "this could not be checked."
                    ),
                )

            same_product = [
                record
                for record in state["application_history"]
                if record.product.lower() == product.name.lower()
            ]

            prior_rate = sum(record.rate_fl_oz_per_acre for record in same_product)
            season_total = prior_rate + plan.proposed_rate

            checks = [
                rule(
                    "field_identity",
                    field.id,
                    lambda: (
                        plan.field_id.strip().casefold() == field.id.strip().casefold()
                    ),
                    "fixable",
                    lambda: (
                        f"The plan uses field {plan.field_id}; "
                        f"the resolved field is {field.id}."
                    ),
                ),
                rule(
                    "product_identity",
                    product.name,
                    lambda: (
                        plan.product_name.strip().casefold()
                        == product.name.strip().casefold()
                    ),
                    "fixable",
                    lambda: (
                        f"The plan uses {plan.product_name}; "
                        f"the resolved product is {product.name}."
                    ),
                ),
                rule(
                    "requested_treatment_date",
                    expected_treatment_date,
                    lambda: plan.treatment_date == expected_treatment_date,
                    "fixable",
                    lambda: (
                        f"The plan date is {plan.treatment_date}; "
                        f"the requested date is {expected_treatment_date}."
                    ),
                ),
                rule(
                    "requested_rate",
                    request.requested_rate,
                    lambda: (
                        request.requested_rate is not None
                        and abs(plan.proposed_rate - request.requested_rate) < 0.000001
                    ),
                    "fixable",
                    lambda: (
                        f"The plan rate is {plan.proposed_rate} fl oz/acre; "
                        f"the requested rate is "
                        f"{request.requested_rate} fl oz/acre."
                    ),
                ),
                rule(
                    "requested_acres",
                    request.acres,
                    lambda: (
                        request.acres is not None
                        and abs(plan.treated_acres - request.acres) < 0.000001
                    ),
                    "fixable",
                    lambda: (
                        f"The plan treats {plan.treated_acres} acres; "
                        f"the request specifies {request.acres} acres."
                    ),
                ),
                rule(
                    "maximum_rate",
                    product.max_rate_fl_oz_per_acre,
                    lambda: (
                        product.max_rate_fl_oz_per_acre is not None
                        and plan.proposed_rate <= product.max_rate_fl_oz_per_acre
                    ),
                    "fixable",
                    lambda: (
                        f"Plan rate is {plan.proposed_rate} fl oz/acre; "
                        f"label maximum is {product.max_rate_fl_oz_per_acre}."
                    ),
                ),
                rule(
                    "seasonal_maximum_rate",
                    product.max_seasonal_fl_oz_per_acre,
                    lambda: (
                        product.max_seasonal_fl_oz_per_acre is not None
                        and season_total <= product.max_seasonal_fl_oz_per_acre
                    ),
                    "fixable",
                    lambda: (
                        f"{prior_rate} fl oz/acre already applied this season, "
                        f"so the total would be {season_total}; label maximum "
                        f"is {product.max_seasonal_fl_oz_per_acre}."
                    ),
                ),
                rule(
                    "applications_per_season",
                    product.max_applications_per_season,
                    lambda: (
                        product.max_applications_per_season is not None
                        and len(same_product) + 1 <= product.max_applications_per_season
                    ),
                    "hard_violation",
                    lambda: (
                        f"This would be application {len(same_product) + 1}; "
                        f"the label allows {product.max_applications_per_season} "
                        "per season."
                    ),
                ),
                rule(
                    "crop_compatibility",
                    product.supported_crops,
                    lambda: (
                        product.supported_crops is not None
                        and field.crop in product.supported_crops
                    ),
                    "hard_violation",
                    lambda: (
                        f"Field is planted to {field.crop}; the label registers "
                        f"{', '.join(product.supported_crops or [])}."
                    ),
                ),
                rule(
                    "trait_compatibility",
                    product.allowed_traits,
                    lambda: (
                        product.allowed_traits is not None
                        and field.trait_package in product.allowed_traits
                    ),
                    "hard_violation",
                    lambda: (
                        f"Field is {field.trait_package.value}; the label allows "
                        f"{', '.join(t.value for t in product.allowed_traits or [])}."
                    ),
                ),
                rule(
                    "growth_stage_window",
                    (
                        product.earliest_growth_stage
                        or product.latest_growth_stage
                        or product.latest_growth_stage_exclusive
                    ),
                    lambda: _stage_in_window(field.growth_stage, product),
                    "hard_violation",
                    lambda: (
                        (
                            f"Field stage {field.growth_stage!r} was not "
                            "recognised, so the label window "
                            f"({_stage_window_describe(product)}) could not be "
                            "checked."
                        )
                        if stage_position(field.growth_stage) is None
                        else (
                            f"Field is at {field.growth_stage}; the label "
                            f"window is {_stage_window_describe(product)}."
                        )
                    ),
                ),
                weather_rule(
                    "wind_maximum",
                    product.wind_max_mph,
                    lambda: (
                        product.wind_max_mph is not None
                        and weather.wind_speed_mph <= product.wind_max_mph
                    ),
                    "fixable",
                    lambda: (
                        f"Forecast wind is {weather.wind_speed_mph} mph; "
                        f"label maximum is {product.wind_max_mph} mph."
                    ),
                ),
                weather_rule(
                    "wind_minimum",
                    product.wind_min_mph,
                    lambda: (
                        product.wind_min_mph is not None
                        and weather.wind_speed_mph >= product.wind_min_mph
                    ),
                    "fixable",
                    lambda: (
                        f"Forecast wind is {weather.wind_speed_mph} mph; "
                        f"the label requires at least {product.wind_min_mph} mph."
                    ),
                ),
                rule(
                    "downwind_buffer",
                    product.downwind_buffer_ft,
                    lambda: (
                        product.downwind_buffer_ft is not None
                        and field.feet_to_sensitive_site >= product.downwind_buffer_ft
                    ),
                    "hard_violation",
                    lambda: (
                        f"Nearest sensitive site is "
                        f"{field.feet_to_sensitive_site} ft; the label requires "
                        f"{product.downwind_buffer_ft} ft."
                    ),
                ),
                rule(
                    "phi_before_harvest",
                    product.phi_days,
                    lambda: (
                        product.phi_days is not None
                        and plan.treatment_date + timedelta(days=product.phi_days)
                        <= field.expected_harvest_date
                    ),
                    "hard_violation",
                    lambda: (
                        "Pre-harvest interval ends on "
                        f"{plan.treatment_date + timedelta(days=product.phi_days or 0)}; "
                        f"expected harvest is {field.expected_harvest_date}."
                    ),
                ),
                rule(
                    "restricted_entry_interval",
                    product.rei_hours,
                    lambda: True,  # recorded for the work order, never a blocker
                    "informational",
                    lambda: (
                        f"Workers may re-enter {product.rei_hours} hours after "
                        f"application, from {plan.treatment_date}."
                    ),
                ),
            ]

            result = RuleEngineResult(
                checks=checks,
                all_passed=all(check.passed for check in checks),
            )

            passed_count = sum(check.passed for check in checks)

            return {
                "rule_result": result,
                "error": None,
                "audit_log": [
                    f"Rule engine completed: {passed_count}/{len(checks)} checks passed."
                ],
            }

        except Exception as exc:
            return {
                "error": f"Rule engine failed: {exc}",
                "audit_log": ["Rule engine failed."],
            }

    def _critic_node(
        self,
        state: AgriculturalState,
    ) -> dict:
        """
        Review the plan and validate the model's verdict against the
        deterministic rule-engine result.
        """

        try:
            evidence_text = "\n\n".join(
                chunk.model_dump_json() for chunk in state["evidence"]
            )

            model_review = self.critic_chain.invoke(
                {
                    "plan": state["plan"].model_dump_json(indent=2),
                    "rule_checks": state["rule_result"].model_dump_json(indent=2),
                    "evidence": evidence_text,
                }
            )

            rule_result = state["rule_result"]

            failed_hard_rules = [
                check
                for check in rule_result.checks
                if (not check.passed and check.severity == "hard_violation")
            ]

            failed_fixable_rules = [
                check
                for check in rule_result.checks
                if (not check.passed and check.severity == "fixable")
            ]

            review = model_review
            validation_message = (
                "Critic verdict agreed with the deterministic rule results."
            )

            if failed_hard_rules:
                failed_names = [check.rule_name for check in failed_hard_rules]

                if model_review.verdict != "hard_violation":
                    review = CriticDecision(
                        verdict="hard_violation",
                        explanation=(
                            "The deterministic rule engine found one or "
                            "more hard compliance violations."
                        ),
                        issues=failed_names,
                        revision_instructions=[],
                        citations=model_review.citations,
                    )

                    validation_message = (
                        "Critic verdict was replaced because the "
                        "deterministic rule engine found hard violations."
                    )

            elif failed_fixable_rules:
                failed_names = [check.rule_name for check in failed_fixable_rules]

                if model_review.verdict != "fixable":
                    review = CriticDecision(
                        verdict="fixable",
                        explanation=(
                            "The deterministic rule engine found one or "
                            "more correctable problems."
                        ),
                        issues=failed_names,
                        revision_instructions=[
                            (
                                "Revise the treatment plan to resolve "
                                f"the {rule_name} rule."
                            )
                            for rule_name in failed_names
                        ],
                        citations=model_review.citations,
                    )

                    validation_message = (
                        "Critic verdict was replaced because the "
                        "deterministic rule engine found fixable failures."
                    )

            elif rule_result.all_passed and model_review.verdict in {
                "fixable",
                "hard_violation",
            }:
                review = CriticDecision(
                    verdict="clean",
                    explanation=(
                        "All deterministic compliance checks passed. "
                        "The original critic verdict contradicted those "
                        "results, so the request may proceed to required "
                        "human review."
                    ),
                    issues=[],
                    revision_instructions=[],
                    citations=state["plan"].citations,
                )

                passed_count = sum(check.passed for check in rule_result.checks)

                validation_message = (
                    "Critic verdict was replaced because it contradicted the "
                    f"{passed_count}/{len(rule_result.checks)} passing "
                    "deterministic rule checks."
                )

            update = {
                "review": review,
                "error": None,
                "audit_log": [
                    (f"Critic returned the {model_review.verdict} verdict."),
                    validation_message,
                    (
                        "Validated critic verdict: "
                        f"{review.verdict}. "
                        f"{review.explanation}"
                    ),
                ],
            }

            if review.verdict == "fixable":
                update["revision_count"] = state.get("revision_count", 0) + 1

            return update

        except Exception as exc:
            return {
                "error": f"Critic failed: {exc}",
                "audit_log": ["Critic failed."],
            }

    @staticmethod
    def _human_review_node(
        state: AgriculturalState,
    ) -> dict:
        decision = interrupt(
            {
                "message": "Human approval is required.",
                "plan": state["plan"].model_dump(),
                "review": state["review"].model_dump(),
                "sources": state.get(
                    "context_sources",
                    [],
                ),
            }
        )

        return {
            "human_decision": decision["decision"],
            "audit_log": [f"Human reviewer selected {decision['decision']}."],
        }

    @staticmethod
    def _work_order_node(state: AgriculturalState) -> dict:
        # import done within function to avoid circular import issues
        # between the workflow and the data layer modules
        from data_layer.work_orders import create_work_order

        result = create_work_order(
            plan=state["plan"],
            thread_id=state.get("thread_id", "unknown"),
        )

        return {
            "work_order": result,
            "final_status": "simulated_work_order_created",
            "final_message": result.message,
            "audit_log": ["Simulated work order created."],
        }

    @staticmethod
    def _rejected_node(
        state: AgriculturalState,
    ) -> dict:
        return {
            "final_status": "rejected",
            "final_message": ("The human reviewer rejected the proposed plan."),
            "audit_log": ["Plan rejected by human reviewer."],
        }

    @staticmethod
    def _escalation_node(
        state: AgriculturalState,
    ) -> dict:
        return {
            "final_status": "escalated",
            "final_message": ("The request requires manual compliance review."),
            "audit_log": ["Request escalated."],
        }

    @staticmethod
    def _failure_node(
        state: AgriculturalState,
    ) -> dict:
        return {
            "final_status": "failed",
            "final_message": state.get(
                "error",
                "An unexpected workflow failure occurred.",
            ),
            "audit_log": ["Workflow ended in a controlled failure."],
        }

    @staticmethod
    def _route_after_intake(
        state: AgriculturalState,
    ) -> Literal[
        "clarify",
        "gather_context",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        if state.get("missing_information"):
            return "clarify"

        return "gather_context"

    @staticmethod
    def _route_after_context(
        state: AgriculturalState,
    ) -> Literal[
        "retrieve",
        "clarify",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        # An unresolved field or product, or a forecast the API cannot supply,
        # is a question for the user rather than a workflow failure.
        if state.get("missing_information"):
            return "clarify"

        return "retrieve"

    @staticmethod
    def _route_after_retrieval(
        state: AgriculturalState,
    ) -> Literal[
        "specialist",
        "clarify",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        if not state.get("evidence"):
            return "clarify"

        return "specialist"

    @staticmethod
    def _route_after_specialist(
        state: AgriculturalState,
    ) -> Literal[
        "refresh_weather",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        return "refresh_weather"

    @staticmethod
    def _route_after_rules(
        state: AgriculturalState,
    ) -> Literal[
        "critic",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        return "critic"

    @staticmethod
    def _route_after_critic(
        state: AgriculturalState,
    ) -> Literal[
        "human_review",
        "specialist",
        "clarify",
        "escalate",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        failed_hard_rules = [
            check
            for check in state["rule_result"].checks
            if (not check.passed and check.severity == "hard_violation")
        ]

        failed_fixable_rules = [
            check
            for check in state["rule_result"].checks
            if (not check.passed and check.severity == "fixable")
        ]

        review = state["review"]

        # Application logic enforces hard violations even if the model
        # returns an inconsistent verdict.
        if failed_hard_rules:
            return "escalate"

        if failed_fixable_rules:
            if state.get("revision_count", 0) <= state.get(
                "max_revisions",
                MAX_REVISIONS,
            ):
                return "specialist"

            return "escalate"

        if review.verdict == "insufficient_info":
            return "clarify"

        return "human_review"

    @staticmethod
    def _route_after_human_review(
        state: AgriculturalState,
    ) -> Literal[
        "write_work_order",
        "rejected",
    ]:
        if state["human_decision"] == "approved":
            return "write_work_order"

        return "rejected"

    def start(
        self,
        question: str,
        thread_id: str,
    ) -> dict:
        config = {
            "configurable": {
                "thread_id": thread_id,
            },
            "recursion_limit": 30,
        }

        return self.graph.invoke(
            {
                "question": question,
                "thread_id": thread_id,
                "messages": [
                    HumanMessage(content=question),
                ],
                "audit_log": [],
                "revision_count": 0,
                "max_revisions": MAX_REVISIONS,
                "error": None,
                "missing_information": [],
            },
            config=config,
        )

    def resume_human_review(
        self,
        decision: Literal[
            "approved",
            "rejected",
        ],
        thread_id: str,
    ) -> dict:
        config = {
            "configurable": {
                "thread_id": thread_id,
            },
            "recursion_limit": 30,
        }

        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be 'approved' or 'rejected'")

        snapshot = self.graph.get_state(config)
        if "human_review" not in snapshot.next:
            raise RuntimeError(f"Thread {thread_id!r} is not awaiting human review.")

        return self.graph.invoke(
            Command(
                resume={
                    "decision": decision,
                }
            ),
            config=config,
        )
