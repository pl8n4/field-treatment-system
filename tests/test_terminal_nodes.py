import re

from graph import AgriculturalWorkflow


def test_work_order_node_creates_simulated_result() -> None:
    update = AgriculturalWorkflow._work_order_node({})

    assert update["final_status"] == "simulated_work_order_created"
    assert update["work_order"].status == "simulated"
    assert re.fullmatch(
        r"DEMO-[0-9A-F]{8}",
        update["work_order"].work_order_id,
    )
    assert "No real treatment was scheduled" in update["final_message"]


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
