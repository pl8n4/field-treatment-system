from __future__ import annotations

from datetime import date
from operator import add
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph, add_messages
# Import to resolve a langgraph serialization issue
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from config import (
    GEMINI_MODEL,
    MODEL_MAX_TOKENS,
    validate_settings,
)

from schemas import (
    TreatmentRequest,
    TriageDecision,
    WorkflowResponse,
)

MAX_CONVERSATION_MESSAGES = 12

TRIAGE_PROMPT = ChatPromptTemplate.from_template(
    """
    You are the intake and triage agent for an agricultural
field-treatment review workflow.

Your responsibilities are:

1. Extract the field-treatment request into the provided schema.
2. Classify the observed issue.
3. Identify required information that is missing.
4. Choose whether the workflow should clarify or retrieve evidence.

Required information:

- field_id
- crop
- observed_issue
- proposed_product
- proposed_date
- acres

Choose exactly one next step:

- retrieve:
  The conversation contains all required information and can proceed
  to agricultural-document retrieval.

- clarify:
  One or more required fields are missing or unclear.

Rules:

- Use the full conversation, including earlier user answers.
- Do not invent missing values.
- Use null for information that was not provided.
- Include every missing required field in missing_information.
- Do not approve or recommend a treatment.
- Do not provide pesticide application instructions.
- If any required field is missing, choose clarify.
- If all required fields are present, choose retrieve.
- Always format proposed_date as YYYY-MM-DD.
- Resolve relative dates such as "today" and "tomorrow" using the supplied current date.
- Do not invent a date tehwn the user did not provide one.
- Always return every top-level field required by the output schema:
  request, issue_type, next_step, missing_information, and routing_reason.
- Always return every field inside request. Use null for unknown values.
- A follow-up message may provide only some missing values. Combine it
  with facts from earlier conversation messages.
- If information is still missing after a follow-up, choose clarify again.
- Return one short business explanation for the route.

CURRENT DATE:

{current_date}

CONVERSATION:

{conversation}
    """.strip()
)

class AgriculturalState(TypedDict, total=False):
    """Shared data that moves through the LangGraph workflow."""

    question: str

    request: TreatmentRequest
    triage: TriageDecision

    final_status: Literal[
        "ready_for_retrieval",
        "needs_information",
        "failed",
    ]

    final_message: str
    error: str | None

    audit_log: Annotated[list[str], add]

    messages: Annotated[list[AnyMessage], add_messages]

    turn_number: int
    turn_start_message_index: int
    turn_start_audit_index: int

class AgriculturalWorkflow:
    """
    Coordinates the agricultural field-treatment review process.
    """

    def __init__(self) -> None:
        validate_settings()

        self.llm = self._build_llm()
        self.triage_chain = self._build_triage_chain()

        # Specific serialization for custom elements
        checkpoint_serializer = JsonPlusSerializer(
            allowed_msgpack_modules=[
                TreatmentRequest,
                TriageDecision,
            ],
        )

        # In-memory persistence
        self.checkpointer = InMemorySaver(
            serde=checkpoint_serializer,
        )

        self.graph = self._build_graph()

    @staticmethod
    def _build_llm() -> ChatGoogleGenerativeAI:
        """
        Create teh hosted Gemini chat model.
        """

        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            max_tokens=MODEL_MAX_TOKENS,
            max_retries=2,
        )
    
    def _build_triage_chain(self):
        """
        Create the structured-output triage chain.
        """

        structured_model = self.llm.with_structured_output(
            TriageDecision,
            method="json_schema",
        )

        base_chain = TRIAGE_PROMPT | structured_model

        return base_chain.with_retry(
            retry_if_exception_type=(Exception,),
            stop_after_attempt=3,
            wait_exponential_jitter=True,
        )
    
    def _build_graph(self):
        """
        Register graph state, nodes, edges, and persistence.
        """

        builder = StateGraph(AgriculturalState)

        builder.add_node(
            "intake",
            self._intake_node,
        )

        builder.add_node(
            "triage",
            self._triage_node,
        )

        builder.add_node(
            "clarify",
            self._clarify_node,
        )

        # TODO: Temporary node. Replace with real RAG retrieval node later.
        builder.add_node(
            "ready_for_retrieval",
            self._ready_for_retrieval_node,
        )

        builder.add_node(
            "failure",
            self._failure_node,
        )

        builder.add_edge(
            START,
            "intake",
        )

        builder.add_conditional_edges(
            "intake",
            self._route_after_intake,
            {
                "triage": "triage",
                "failure": "failure",
            },
        )

        builder.add_conditional_edges(
            "triage",
            self._route_after_triage,
            {
                "retrieve": "ready_for_retrieval",
                "clarify": "clarify",
                "failure": "failure",
            },
        )

        builder.add_edge(
            "ready_for_retrieval",
            END,
        )

        builder.add_edge(
            "clarify",
            END,
        )

        builder.add_edge(
            "failure",
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
        messages: list[AnyMessage],
    ) -> str:
        """
        Format recent messages for the triage prompt.
        """

        formatted_messages: list[str] = []

        for message in messages[-MAX_CONVERSATION_MESSAGES:]:
            if isinstance(message, HumanMessage):
                role = "User"
            elif isinstance(message, AIMessage):
                role = "Assistant"
            else:
                role = "System"
            
            content = self._content_to_text(message.content)
            formatted_messages.append(f"{role}: {content}")

        return "\n".join(formatted_messages)
    
    @staticmethod
    def _intake_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Validate and normalize the current request.
        """

        try:
            normalized_question = state["question"].strip()

            if not normalized_question:
                raise ValueError(
                    "The field-treatment request cannot be empty"
                )
            
            turn_start_message_index = max(
                len(state.get("messages", [])) - 1,
                0,
            )

            return {
                "question": normalized_question,
                "error": None,
                "turn_number": state.get("turn_number", 0) + 1,
                "turn_start_message_index": (
                    turn_start_message_index
                ),
                "turn_start_audit_index": len(
                    state.get("audit_log", [])
                ),
                "audit_log": [
                    "Intake normalized and validated the request."
                ],
            }
        
        except Exception as exc:
            return {
                "error": f"Intake failed: {exc}",
                "audit_log": [
                    "Intake failed to validate the request."
                ],
            }
        
    def _triage_node(
        self,
        state: AgriculturalState, 
    ) -> dict:
        """
        Extract, classify, and route the treatment request.
        """

        try:
            conversation = self._format_conversation(
                state.get("messages", [])
            )

            triage = self.triage_chain.invoke(
                {
                    "conversation": conversation,
                    "current_date": date.today().isoformat(),
                }
            )

            return {
                "request": triage.request,
                "triage": triage,
                "error": None,
                "audit_log": [
                    (
                        "Triage classified the issue as "
                        f"{triage.issue_type} and selected the "
                        f"{triage.next_step} route."
                    )
                ],
            }
        
        except Exception as exc:
            return {
                "error": f"Triage agent failed: {exc}",
                "audit_log": [
                    "Triage failed to process the request."
                ],
            }
        
    @staticmethod
    def _clarify_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Stop and request missing information from the user.
        """

        triage = state["triage"]

        missing_information = (
            triage.missing_information
            or ["Additional field-treatment details"]
        )

        readable_missing_information = ", ".join(
            item.replace("_", " ")
            for item in missing_information
        )

        final_message = (
            "The workflow needs the following information before "
            f"continuing: {readable_missing_information}."
        )

        return {
            "final_status": "needs_information",
            "final_message": final_message,
            "messages": [
                AIMessage(content=final_message),
            ],
            "audit_log": [
                (
                    "Clarification stopped the workflow and requested "
                    "missing information."
                )
            ],
        }

    @staticmethod
    def _ready_for_retrieval_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Temporary endpoint until RAG retrieval is connected.
        """

        final_message = (
            "The request contains the required information and is ready for agricultural-document retrieval."
        )

        return {
            "final_status": "ready_for_retrieval",
            "final_message": final_message,
            "messages": [
                AIMessage(content=final_message),
            ],
            "audit_log": [
                "The request was approved for evidence retrieval."
            ],
        }
    
    @staticmethod
    def _failure_node(
        state: AgriculturalState,
    ) -> dict:
        """
        Return a controlled workflow failure.
        """

        final_message = state.get(
            "error",
            "An unexpected workflow error occurred.",
        )

        return {
            "final_status": "failed",
            "final_message": final_message,
            "messages": [
                AIMessage(content=final_message),
            ],
            "audit_log": [
                "The workflow ended in a controlled failure."
            ],
        }
    
    @staticmethod
    def _route_after_intake(
        state: AgriculturalState,
    ) -> Literal[
        "triage",
        "failure",
    ]:
        """
        Choose the next route after intake.
        """

        if state.get("error"):
            return "failure"
        
        return "triage"
    
    @staticmethod
    def _route_after_triage(
        state: AgriculturalState,
    ) -> Literal[
        "retrieve",
        "clarify",
        "failure",
    ]:
        """
        Choose the next route after triage.
        """

        if state.get("error"):
            return "failure"
        
        return state["triage"].next_step
    
    def process_request(
        self,
        question: str,
        thread_id: str,
    ) -> WorkflowResponse:
        """
        Invoke the workflow for one conversation turn.
        """

        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        final_state = self.graph.invoke(
            {
                "question": question,
                "messages": [
                    HumanMessage(content=question),
                ],
                "audit_log": [],
                "error": None,
            },
            config=config,
        )

        workflow_failed = final_state["final_status"] == "failed"

        return WorkflowResponse(
            thread_id=thread_id,
            question=final_state["question"],
            request=(
                None
                if workflow_failed
                else final_state.get("request")
            ),
            triage=(
                None
                if workflow_failed
                else final_state.get("triage")
            ),
            final_status=final_state["final_status"],
            final_message=final_state["final_message"],
            audit_log=final_state["audit_log"],
            turn_number=final_state.get("turn_number", 1),
            conversation_message_count=len(
                final_state.get("messages", [])
            ),
        )
