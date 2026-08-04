from typing import Any

from workflow.graph import AgriculturalWorkflow
from workflow.schemas import IntakeDecision, TreatmentRequest


class FakeChain:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.inputs: dict[str, Any] | None = None

    def invoke(self, inputs: dict[str, Any]) -> Any:
        self.inputs = inputs
        return self.result


def workflow_with_intake(result: IntakeDecision) -> AgriculturalWorkflow:
    workflow = AgriculturalWorkflow.__new__(AgriculturalWorkflow)
    workflow.intake_chain = FakeChain(result)
    return workflow


def test_intake_uses_deterministic_required_fields() -> None:
    decision = IntakeDecision(
        request=TreatmentRequest(
            field_id="F001",
            observed_issue="fungal disease",
            proposed_product="Example Product",
            proposed_date="2026-08-02",
        ),
        issue_type="disease",
        next_step="clarify",
        user_required_information=["requested_rate"],
        system_fillable_information=[],
        routing_reason="The model incorrectly requested a rate.",
    )
    workflow = workflow_with_intake(decision)

    update = workflow._intake_node(
        {
            "question": "Treat F001 with Example Product today.",
            "messages": [],
        }
    )

    assert update["error"] is None
    assert update["missing_information"] == []
    assert AgriculturalWorkflow._route_after_intake(update) == "gather_context"


def test_intake_reports_missing_user_required_fields() -> None:
    decision = IntakeDecision(
        request=TreatmentRequest(
            field_id="F001",
            observed_issue="fungal disease",
        ),
        issue_type="disease",
        next_step="gather_context",
        user_required_information=[],
        system_fillable_information=[],
        routing_reason="The model incorrectly selected context gathering.",
    )
    workflow = workflow_with_intake(decision)

    update = workflow._intake_node(
        {
            "question": "Field F001 has a fungal disease.",
            "messages": [],
        }
    )

    assert update["missing_information"] == [
        "proposed_product",
        "proposed_date",
    ]
    assert AgriculturalWorkflow._route_after_intake(update) == "clarify"


def test_intake_converts_blank_question_to_controlled_failure() -> None:
    decision = IntakeDecision(
        request=TreatmentRequest(),
        issue_type="unknown",
        next_step="clarify",
        routing_reason="Unused test response.",
    )
    workflow = workflow_with_intake(decision)

    update = workflow._intake_node({"question": "   ", "messages": []})

    assert update["error"] == "Intake failed: The request cannot be empty"
    assert AgriculturalWorkflow._route_after_intake(update) == "failure"
