import re
from unittest.mock import patch

from workflow.graph import AgriculturalWorkflow
from workflow.schemas import TreatmentPlan, WorkOrderResult


def test_work_order_node_creates_simulated_result(
    treatment_plan: TreatmentPlan,
) -> None:
    work_order = WorkOrderResult(
        work_order_id="WO-1234ABCD",
        status="simulated",
        message=(
            "A simulated work-order record was created. "
            "No real treatment was scheduled."
        ),
    )

    with patch(
        "data_layer.work_orders.create_work_order",
        return_value=work_order,
    ) as create_work_order:
        update = AgriculturalWorkflow._work_order_node(
            {
                "plan": treatment_plan,
                "thread_id": "test-thread-id",
            }
        )

    assert update["final_status"] == "simulated_work_order_created"
    assert update["work_order"].status == "simulated"
    assert re.fullmatch(
        r"WO-[0-9A-F]{8}",
        update["work_order"].work_order_id,
    )
    assert "No real treatment was scheduled" in update["final_message"]
    create_work_order.assert_called_once_with(
        plan=treatment_plan,
        thread_id="test-thread-id",
    )


def test_rejected_node_returns_terminal_status() -> None:
    update = AgriculturalWorkflow._rejected_node({})

    assert update["final_status"] == "rejected"
    assert "rejected" in update["final_message"]


def test_escalation_node_returns_terminal_status() -> None:
    update = AgriculturalWorkflow._escalation_node({})

    assert update["final_status"] == "escalated"
    assert "manual compliance review" in update["final_message"]


def test_failure_node_uses_recorded_error() -> None:
    update = AgriculturalWorkflow._failure_node({"error": "Test failure"})

    assert update["final_status"] == "failed"
    assert update["final_message"] == "Test failure"
