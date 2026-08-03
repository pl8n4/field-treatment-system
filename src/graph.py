from __future__ import annotations

from datetime import date, timedelta
from operator import add
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

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

from config import (
    GEMINI_MODEL,
    MODEL_MAX_TOKENS,
    MODEL_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    validate_settings,
)
from schemas import (
    ApplicationRecord,
    CriticDecision,
    EvidenceChunk,
    FieldRecord,
    IntakeDecision,
    ProductRecord,
    RuleCheck,
    RuleEngineResult,
    TreatmentPlan,
    TreatmentRequest,
    WeatherForecast,
    WorkOrderResult,
)

MAX_REVISIONS = 1
MAX_CONVERSATION_MESSAGES = 12

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
- Use the requested rate when one was supplied unless previous review
  feedback requires correction.
- When no rate was requested, choose a rate within the structured
  product limits.
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
    field_record: FieldRecord
    product_record: ProductRecord
    application_history: list[ApplicationRecord]
    weather: WeatherForecast

    # Retrieved knowledge
    evidence: list[EvidenceChunk]
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
                FieldRecord,
                ProductRecord,
                ApplicationRecord,
                WeatherForecast,
                EvidenceChunk,
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
                "rules": "rules",
                "failure": "failure",
            },
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

    # TODO: Replace mock integration with real integration
    @staticmethod
    def _gather_context_node(
        state: AgriculturalState,
    ) -> dict:
        """
        MOCK INTEGRATION POINT

        Replace this body with:
        - field lookup
        - product lookup
        - application-history lookup
        - weather lookup
        """

        try:
            request = state["request"]

            proposed_date = (
                date.fromisoformat(request.proposed_date)
                if request.proposed_date
                else date.today()
            )

            field = FieldRecord(
                field_id=request.field_id or "UNKNOWN",
                crop=request.crop or "soybeans",
                acres=request.acres or 80,
                trait_package="Example Trait",
                growth_stage="R2",
                expected_harvest_date=(date.today() + timedelta(days=60)),
                latitude=41.6,
                longitude=-93.6,
                sensitive_site_distance_feet=300,
            )

            product = ProductRecord(
                product_name=(request.proposed_product or "Example Product"),
                supported_crops=[
                    "soybeans",
                ],
                compatible_traits=[
                    "Example Trait",
                ],
                allowed_growth_stages=[
                    "V6",
                    "R1",
                    "R2",
                ],
                minimum_rate=10,
                maximum_rate=20,
                seasonal_maximum_rate=40,
                maximum_wind_mph=15,
                maximum_temperature_f=90,
                required_buffer_feet=110,
                rei_hours=24,
                phi_days=30,
            )

            history = [
                ApplicationRecord(
                    field_id=field.field_id,
                    product_name=product.product_name,
                    application_date=(date.today() - timedelta(days=30)),
                    rate=10,
                )
            ]

            weather = WeatherForecast(
                forecast_date=proposed_date,
                high_temperature_f=82,
                wind_speed_mph=8,
                wind_direction="NW",
                precipitation_probability=20,
                source="Mock Open-Meteo response",
                cached=True,
            )

            return {
                "field_record": field,
                "product_record": product,
                "application_history": history,
                "weather": weather,
                "error": None,
                "audit_log": [
                    "Mock field, product, application-history, and weather context loaded."
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
        MOCK INTEGRATION POINT

        Replace this body with the Chroma retriever.
        """

        try:
            product = state["product_record"]

            evidence = [
                EvidenceChunk(
                    content=(
                        "Mock label evidence: application must remain within the structured product rate limits."
                    ),
                    source="mock_product_label.pdf",
                    page=4,
                    product_name=product.product_name,
                    registration_number="00000-000",
                ),
                EvidenceChunk(
                    content=(
                        "Mock label evidence: observe the required buffer, REI, PHI, wind, and temperature limits."
                    ),
                    source="mock_product_label.pdf",
                    page=7,
                    product_name=product.product_name,
                    registration_number="00000-000",
                ),
            ]

            sources = sorted({chunk.source for chunk in evidence})

            return {
                "evidence": evidence,
                "context_sources": sources,
                "missing_information": (
                    [] if evidence else ["Applicable product-label evidence"]
                ),
                "error": None,
                "audit_log": [
                    f"Mock retrieval return {len(evidence)} chunks from {len(sources)} sources."
                ],
            }

        except Exception as exc:
            return {
                "error": f"Retrieval failed: {exc}",
                "audit_log": ["Retrieval failed."],
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
        MOCK INTEGRATION POINT

        Replace this implementation with the team's final rule engine.
        """

        try:
            plan = state["plan"]
            product = state["product_record"]
            field = state["field_record"]
            weather = state["weather"]

            prior_product_rate = sum(
                record.rate
                for record in state["application_history"]
                if (record.product_name.lower() == product.product_name.lower())
            )

            phi_deadline = plan.treatment_date + timedelta(days=product.phi_days)

            checks = [
                RuleCheck(
                    rule_name="maximum_rate",
                    passed=(plan.proposed_rate <= product.maximum_rate),
                    severity="fixable",
                    explanation=(
                        f"Plan rate is {plan.proposed_rate}; "
                        f"maximum is {product.maximum_rate}."
                    ),
                ),
                RuleCheck(
                    rule_name="seasonal_maximum_rate",
                    passed=(
                        prior_product_rate + plan.proposed_rate
                        <= product.seasonal_maximum_rate
                    ),
                    severity="fixable",
                    explanation=(
                        "Seasonal total would be "
                        f"{prior_product_rate + plan.proposed_rate}; "
                        f"maximum is {product.seasonal_maximum_rate}."
                    ),
                ),
                RuleCheck(
                    rule_name="crop_compatibility",
                    passed=(field.crop in product.supported_crops),
                    severity="hard_violation",
                    explanation=(
                        f"Field crop is {field.crop}; supported crops "
                        f"are {', '.join(product.supported_crops)}."
                    ),
                ),
                RuleCheck(
                    rule_name="trait_compatibility",
                    passed=(field.trait_package in product.compatible_traits),
                    severity="hard_violation",
                    explanation=(
                        f"Field trait is {field.trait_package}; "
                        "compatible traits are "
                        f"{', '.join(product.compatible_traits)}."
                    ),
                ),
                RuleCheck(
                    rule_name="growth_stage",
                    passed=(field.growth_stage in product.allowed_growth_stages),
                    severity="hard_violation",
                    explanation=(
                        f"Growth stage is {field.growth_stage}; "
                        "allowed stages are "
                        f"{', '.join(product.allowed_growth_stages)}."
                    ),
                ),
                RuleCheck(
                    rule_name="wind",
                    passed=(weather.wind_speed_mph <= product.maximum_wind_mph),
                    severity="fixable",
                    explanation=(
                        f"Forecast wind is {weather.wind_speed_mph} mph; "
                        f"maximum is {product.maximum_wind_mph} mph."
                    ),
                ),
                RuleCheck(
                    rule_name="temperature",
                    passed=(
                        weather.high_temperature_f <= product.maximum_temperature_f
                    ),
                    severity="fixable",
                    explanation=(
                        "Forecast high is "
                        f"{weather.high_temperature_f} F; "
                        "maximum is "
                        f"{product.maximum_temperature_f} F."
                    ),
                ),
                RuleCheck(
                    rule_name="buffer",
                    passed=(
                        field.sensitive_site_distance_feet
                        >= product.required_buffer_feet
                    ),
                    severity="hard_violation",
                    explanation=(
                        "Sensitive-site distance is "
                        f"{field.sensitive_site_distance_feet} feet; "
                        "required buffer is "
                        f"{product.required_buffer_feet} feet."
                    ),
                ),
                RuleCheck(
                    rule_name="phi_before_harvest",
                    passed=(phi_deadline <= field.expected_harvest_date),
                    severity="hard_violation",
                    explanation=(
                        f"PHI ends on {phi_deadline}; expected harvest "
                        f"is {field.expected_harvest_date}."
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
                    (
                        f"Rule engine completed: {passed_count}/"
                        f"{len(checks)} checks passed."
                    )
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

                validation_message = (
                    "Critic verdict was replaced because it contradicted "
                    "the 9/9 passing deterministic rule checks."
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
    def _work_order_node(
        state: AgriculturalState,
    ) -> dict:
        """
        MOCK SIDE EFFECT

        Replace this with the team's work-order writer.
        """

        result = WorkOrderResult(
            work_order_id=(f"DEMO-{uuid4().hex[:8].upper()}"),
            status="simulated",
            message=(
                "A simulated work-order record was created. "
                "No real treatment was scheduled."
            ),
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
        "failure",
    ]:
        if state.get("error"):
            return "failure"

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
        "rules",
        "failure",
    ]:
        if state.get("error"):
            return "failure"

        return "rules"

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

        return self.graph.invoke(
            Command(
                resume={
                    "decision": decision,
                }
            ),
            config=config,
        )
