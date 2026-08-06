from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

import data_layer.work_orders as work_orders
from workflow.schemas import CriticDecision, TreatmentPlan


class FakeWorkflow:
    def __init__(
        self,
        *,
        start_result: dict[str, Any] | None = None,
        resume_result: dict[str, Any] | None = None,
    ) -> None:
        self.start_result = start_result or {}
        self.resume_result = resume_result or {}
        self.start_calls: list[tuple[str, str]] = []
        self.resume_calls: list[tuple[str, str]] = []

    def start(self, question: str, thread_id: str) -> dict[str, Any]:
        self.start_calls.append((question, thread_id))
        return self.start_result

    def resume_human_review(
        self,
        decision: str,
        thread_id: str,
    ) -> dict[str, Any]:
        self.resume_calls.append((decision, thread_id))
        return self.resume_result


def configured_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    workflow: FakeWorkflow | None = None,
) -> AppTest:
    monkeypatch.setattr(work_orders, "DB_PATH", tmp_path / "work_orders.db")
    app = AppTest.from_file("app.py")
    if workflow is not None:
        app.session_state["workflow"] = workflow
        app.session_state["thread_id"] = "test-thread"
        app.session_state["awaiting_review"] = False
        app.session_state["last_state"] = None
    return app.run(timeout=30)


def button_with_label(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def text_area_with_label(app: AppTest, label: str):
    return next(area for area in app.text_area if area.label == label)


def test_streamlit_app_starts_with_empty_work_order_queue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = configured_app(monkeypatch, tmp_path)

    assert not app.exception
    assert app.title[0].value == "AgriFlow AI"
    assert [selectbox.label for selectbox in app.selectbox] == [
        "Crop",
        "Product",
        "State / Location",
        "Field ID",
    ]
    assert "thread_id" in app.session_state
    assert "workflow" in app.session_state
    assert "No work orders have been created yet." in [info.value for info in app.info]


def test_streamlit_submission_uses_current_thread(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow = FakeWorkflow(
        start_result={
            "final_status": "needs_information",
            "final_message": "More information is required.",
            "missing_information": ["proposed date"],
        }
    )
    app = configured_app(monkeypatch, tmp_path, workflow)

    text_area_with_label(app, "Treatment Request").set_value("Treat the weeds.")
    button_with_label(app, "Submit").click()
    app.run(timeout=30)

    assert len(workflow.start_calls) == 1
    request, thread_id = workflow.start_calls[0]
    assert "Treat the weeds." in request
    assert "The field ID is F-01." in request
    assert "The proposed product is Paraquat 43.2% SL." in request
    assert thread_id == "test-thread"
    assert app.session_state["last_state"]["final_status"] == "needs_information"
    assert app.session_state["thread_id"] == "test-thread"


def test_streamlit_submission_enters_human_review_on_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow = FakeWorkflow(
        start_result={"__interrupt__": ["review"], "plan": {}, "review": {}}
    )
    app = configured_app(monkeypatch, tmp_path, workflow)

    text_area_with_label(app, "Treatment Request").set_value("Treat the weeds.")
    button_with_label(app, "Submit").click()
    app.run(timeout=30)

    assert app.session_state["awaiting_review"] is True


def test_streamlit_rejects_blank_submission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow = FakeWorkflow()
    app = configured_app(monkeypatch, tmp_path, workflow)

    button_with_label(app, "Submit").click()
    app.run(timeout=30)

    assert workflow.start_calls == []
    assert "Please provide: treatment request." in [
        warning.value for warning in app.warning
    ]


@pytest.mark.parametrize("invalid_rate", ["0", "-1", "not a number"])
def test_streamlit_rejects_invalid_application_rate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    invalid_rate: str,
) -> None:
    workflow = FakeWorkflow()
    app = configured_app(monkeypatch, tmp_path, workflow)

    text_area_with_label(app, "Treatment Request").set_value("Treat the weeds.")
    next(item for item in app.text_input if item.label == "Application Rate").set_value(
        invalid_rate
    )
    button_with_label(app, "Submit").click()
    app.run(timeout=30)

    assert workflow.start_calls == []
    assert "Application rate must be a number greater than zero." in [
        warning.value for warning in app.warning
    ]


def test_streamlit_followup_resumes_same_conversation_thread(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow = FakeWorkflow(
        start_result={
            "__interrupt__": ["review"],
            "plan": {},
            "review": {},
        }
    )
    app = configured_app(monkeypatch, tmp_path, workflow)
    app.session_state["last_state"] = {
        "final_status": "needs_information",
        "final_message": "A date is required.",
        "missing_information": ["proposed date"],
    }
    app.run(timeout=30)

    text_area_with_label(app, "Follow-up response").set_value("Use August 6, 2026.")
    button_with_label(app, "Continue").click()
    app.run(timeout=30)

    assert workflow.start_calls == [("Use August 6, 2026.", "test-thread")]
    assert app.session_state["awaiting_review"] is True


def test_streamlit_followup_without_interrupt_displays_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow = FakeWorkflow(
        start_result={
            "final_status": "escalated",
            "final_message": "Manual review is required.",
        }
    )
    app = configured_app(monkeypatch, tmp_path, workflow)
    app.session_state["last_state"] = {
        "final_status": "needs_information",
        "final_message": "A date is required.",
    }
    app.run(timeout=30)

    text_area_with_label(app, "Follow-up response").set_value("Use August 6, 2026.")
    button_with_label(app, "Continue").click()
    app.run(timeout=30)

    assert app.session_state["awaiting_review"] is False
    assert app.session_state["last_state"]["final_status"] == "escalated"


def test_streamlit_renders_pydantic_plan_and_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    treatment_plan: TreatmentPlan,
) -> None:
    app = configured_app(monkeypatch, tmp_path, FakeWorkflow())
    plan_without_optional_lists = treatment_plan.model_copy(
        update={"assumptions": [], "citations": []}
    )
    app.session_state["awaiting_review"] = True
    app.session_state["last_state"] = {
        "plan": plan_without_optional_lists,
        "review": CriticDecision(
            verdict="clean",
            explanation="All checks passed.",
        ),
    }

    app.run(timeout=30)

    assert not app.exception
    assert any(
        plan_without_optional_lists.field_id in item.value for item in app.markdown
    )


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_streamlit_human_review_uses_current_thread_and_rotates_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    decision: str,
) -> None:
    workflow = FakeWorkflow(
        resume_result={
            "final_status": (
                "simulated_work_order_created" if decision == "approved" else "rejected"
            ),
            "final_message": "Review completed.",
        }
    )
    app = configured_app(monkeypatch, tmp_path, workflow)
    app.session_state["awaiting_review"] = True
    app.session_state["last_state"] = {
        "plan": {
            "field_id": "F-02",
            "product_name": "Enlist One",
            "treatment_date": "2026-08-06",
            "proposed_rate": 32,
            "treated_acres": 40,
            "timing_summary": "Timing is compliant.",
            "buffer_summary": "Buffer is compliant.",
            "rei_summary": "REI is 12 hours.",
            "phi_summary": "PHI is compliant.",
            "assumptions": ["Test assumption"],
            "citations": ["label.pdf, page 1"],
        },
        "review": {
            "verdict": "clean",
            "explanation": "All checks passed.",
            "issues": ["Test issue for display"],
        },
        "context_sources": ["label.pdf"],
    }
    app.run(timeout=30)

    button_label = "Accept" if decision == "approved" else "Decline"
    button_with_label(app, button_label).click()
    app.run(timeout=30)

    assert workflow.resume_calls == [(decision, "test-thread")]
    assert app.session_state["awaiting_review"] is False
    assert app.session_state["thread_id"] != "test-thread"


def test_streamlit_renders_and_resets_completed_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = configured_app(monkeypatch, tmp_path, FakeWorkflow())
    app.session_state["last_state"] = {
        "final_status": "simulated_work_order_created",
        "final_message": "Created.",
        "work_order": {
            "work_order_id": "WO-1234ABCD",
            "status": "simulated",
            "message": "Created.",
        },
        "audit_log": ["Completed test workflow."],
    }
    app.run(timeout=30)

    assert any("WO-1234ABCD" in markdown.value for markdown in app.markdown)
    original_thread = app.session_state["thread_id"]
    button_with_label(app, "Start new request").click()
    app.run(timeout=30)

    assert app.session_state["last_state"] is None
    assert app.session_state["thread_id"] != original_thread


def test_streamlit_renders_stored_work_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    treatment_plan: TreatmentPlan,
) -> None:
    database_path = tmp_path / "work_orders.db"
    monkeypatch.setattr(work_orders, "DB_PATH", database_path)
    work_orders.init_db()
    result = work_orders.create_work_order(treatment_plan, "queue-thread")

    app = AppTest.from_file("app.py").run(timeout=30)

    assert not app.exception
    assert any(result.work_order_id in expander.label for expander in app.expander)
