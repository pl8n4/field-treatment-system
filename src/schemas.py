from typing import Literal
from pydantic import BaseModel, Field
from datetime import date

class TreatmentRequest(BaseModel):
    """
    Structured agricultural field-treatment request.
    """

    field_id: str | None = Field(
        default=None,
        description="Unique identifier for the agriculural field",
    )

    crop: str | None = Field(
        default=None,
        description="Crop currently growing in the field",
    )

    observed_issue: str | None = Field(
        default=None,
        description=(
            "Observed disease, insect, weed, nutrient, "
            "or other field issue"
        ),
    )

    proposed_product: str | None = Field(
        default=None,
        description="Product proposed for the field treatment",
    )

    proposed_date: str | None = Field(
        default=None,
        description=(
            "Requested treatment date as an ISO date in "
            "YYYY-MM-DD format"
        )
    )

    acres: float | None = Field(
        default=None,
        description="Number of acres to be treated",
    )

class TriageDecision(BaseModel):
    """
    Structured result produced by the triage agent.
    """

    request: TreatmentRequest

    issue_type: Literal[
        "disease",
        "insect",
        "weed",
        "nutrient",
        "unknown"
    ]

    next_step: Literal[
        "clarify",
        "retrieve",
    ]

    missing_information: list[str] = Field(
        default_factory=list,
        description="Required information missing from the request",
    )

    routing_reason: str = Field(
        description=(
            "One short business explanation for the selected route."
            "Do not provide hidden chain-of-thought reasoning."
        )
    )

class WorkflowResponse(BaseModel):
    """
    Response returned by the LangGraph workflow.
    """

    thread_id: str
    question: str
    request: TreatmentRequest | None
    triage: TriageDecision | None

    final_status: Literal[
        "ready_for_retrieval",
        "needs_information",
        "failed",
    ]

    final_message: str
    audit_log: list[str]
    turn_number: int
    conversation_message_count: int