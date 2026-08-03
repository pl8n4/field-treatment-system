from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# Farm records, label evidence, and weather live in data_layer.schemas:
# FarmField, ProductLimits, Application, LabelChunk, WeatherForecast.
# This module holds only the schemas the workflow itself owns.

# INTAKE


class TreatmentRequest(BaseModel):
    """
    Structured agricultural field-treatment request.
    """

    field_id: str | None = Field(
        default=None,
        description="Unique field identifier",
    )

    crop: str | None = Field(
        default=None,
        description="Crop currently growing in the field",
    )

    observed_issue: str | None = Field(
        default=None,
        description="Observed pest, disease, weed, or nutrient issue",
    )

    proposed_product: str | None = Field(
        default=None,
        description="Product proposed for treatment",
    )

    proposed_date: str | None = Field(
        default=None,
        description=("Requested treatment date as an ISO date in YYYY-MM-DD format"),
    )

    acres: float | None = Field(
        default=None,
        gt=0,
        description="Number of acres to be treated",
    )

    requested_rate: float | None = Field(
        default=None,
        gt=0,
        description="Requested application rate, when provided",
    )


class IntakeDecision(BaseModel):
    """
    Structured result produced by the intake parser.
    """

    request: TreatmentRequest

    issue_type: Literal["disease", "insect", "weed", "nutrient", "unknown"]

    next_step: Literal[
        "clarify",
        "gather_context",
    ]

    user_required_information: list[str] = Field(default_factory=list)

    system_fillable_information: list[str] = Field(default_factory=list)

    routing_reason: str


# SPECIALIST


class TreatmentPlan(BaseModel):
    field_id: str
    product_name: str
    treatment_date: date

    proposed_rate: float = Field(
        gt=0,
        description="Proposed application rate; must be greater than zero",
    )
    treated_acres: float = Field(
        gt=0, description="Number of treated acres; must be greater than zero."
    )

    timing_summary: str
    buffer_summary: str
    rei_summary: str
    phi_summary: str

    citations: list[str]
    assumptions: list[str] = Field(default_factory=list)

    human_review_required: bool = True


# RULE ENGINE AND CRITIC


class RuleCheck(BaseModel):
    rule_name: str
    passed: bool

    severity: Literal[
        "informational",
        "fixable",
        "hard_violation",
    ]

    explanation: str


class RuleEngineResult(BaseModel):
    checks: list[RuleCheck]
    all_passed: bool


class CriticDecision(BaseModel):
    verdict: Literal[
        "clean",
        "fixable",
        "insufficient_info",
        "hard_violation",
    ]

    explanation: str

    issues: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


# HUMAN REVIEW AND MOCKED SIDE EFFECT


class WorkOrderResult(BaseModel):
    work_order_id: str
    status: Literal["simulated"]
    message: str


# APPLICATION RESPONSE


class WorkflowResponse(BaseModel):
    """
    Response returned by the LangGraph workflow.
    """

    thread_id: str
    question: str
    request: TreatmentRequest | None
    plan: TreatmentPlan | None = None
    review: CriticDecision | None = None
    work_order: WorkOrderResult | None = None

    revision_count: int = 0
    audit_log: list[str] = Field(default_factory=list)
