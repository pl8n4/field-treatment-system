from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

import data_layer.work_orders as work_orders
from data_layer.schemas import (
    Application,
    FarmField,
    LabelChunk,
    ProductLimits,
    WeatherForecast,
)
from workflow.schemas import (
    CriticDecision,
    RuleCheck,
    RuleEngineResult,
    TreatmentPlan,
)

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
QUEUE_PAGE_PATH = Path(__file__).resolve().parent / "harnesses" / "queue_page.py"


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
        self.reported_nodes: list[str] = []

    def start(
        self,
        question: str,
        thread_id: str,
        on_node: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        self.start_calls.append((question, thread_id))
        if on_node is not None:
            for node in self.start_result.get("audit_log", []) or []:
                on_node(node)
                self.reported_nodes.append(node)
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
    app = AppTest.from_file(APP_PATH)
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


def text_input_with_label(app: AppTest, label: str):
    return next(item for item in app.text_input if item.label == label)


def test_streamlit_app_starts_on_the_intake_form(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = configured_app(monkeypatch, tmp_path)

    assert not app.exception
    assert app.title[0].value == "New treatment request"
    assert [selectbox.label for selectbox in app.selectbox] == [
        "Crop",
        "Field ID",
        "State / Location",
        "Product",
    ]
    assert "thread_id" in app.session_state
    assert "workflow" in app.session_state


def test_streamlit_work_order_page_starts_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(work_orders, "DB_PATH", tmp_path / "work_orders.db")

    app = AppTest.from_file(QUEUE_PAGE_PATH).run(timeout=30)

    assert not app.exception
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
    button_with_label(app, "Submit request").click()
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
    button_with_label(app, "Submit request").click()
    app.run(timeout=30)

    assert app.session_state["awaiting_review"] is True


def test_streamlit_rejects_blank_submission_with_an_inline_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow = FakeWorkflow()
    app = configured_app(monkeypatch, tmp_path, workflow)

    button_with_label(app, "Submit request").click()
    app.run(timeout=30)

    assert workflow.start_calls == []
    assert "Enter the treatment request." in [error.value for error in app.error]


def test_streamlit_other_crop_input_appears_without_submitting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Choosing "Other" must reveal its input immediately.

    The fields used to live inside an st.form, which suppresses reruns, so the
    revealed input only appeared after a submit that had already failed.
    """
    workflow = FakeWorkflow()
    app = configured_app(monkeypatch, tmp_path, workflow)

    assert "Other crop" not in [item.label for item in app.text_input]

    next(box for box in app.selectbox if box.label == "Crop").set_value("Other")
    app.run(timeout=30)

    assert "Other crop" in [item.label for item in app.text_input]

    text_input_with_label(app, "Other crop").set_value("Sorghum")
    text_area_with_label(app, "Treatment Request").set_value("Treat the weeds.")
    button_with_label(app, "Submit request").click()
    app.run(timeout=30)

    assert len(workflow.start_calls) == 1
    assert "The crop is Sorghum." in workflow.start_calls[0][0]


def test_rate_and_acreage_placeholders_show_the_real_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The greyed value must be the default that will actually be used.

    Both are shown rather than pre-filled: an empty input means "unspecified",
    which is what lets the workflow fall back to its own records.
    """
    app = configured_app(monkeypatch, tmp_path, FakeWorkflow())

    def placeholders() -> dict[str, str | None]:
        return {item.label: item.placeholder for item in app.number_input}

    next(box for box in app.selectbox if box.label == "Field ID").set_value(
        "F-02 — Hartley South"
    )
    next(box for box in app.selectbox if box.label == "Product").set_value("Enlist One")
    app.run(timeout=30)

    # Enlist One's label default rate, and F-02's recorded acreage.
    assert placeholders()["Application rate (fl oz/acre)"] == "32 (default)"
    assert placeholders()["Area to treat (acres)"] == "96.5 (default)"

    # A product with no record on file has no default to show.
    next(box for box in app.selectbox if box.label == "Product").set_value("Other")
    app.run(timeout=30)

    assert (
        placeholders()["Application rate (fl oz/acre)"]
        == "Defaults to the product label's default"
    )

    # Leaving both empty keeps them out of the workflow's request entirely.
    text_area_with_label(app, "Treatment Request").set_value("Treat the weeds.")
    text_input_with_label(app, "Other product").set_value("Enlist One")
    button_with_label(app, "Submit request").click()
    app.run(timeout=30)

    request = app.session_state["workflow"].start_calls[0][0]
    assert "acres" not in request
    assert "application rate" not in request


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


def test_clarification_can_be_abandoned_without_answering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A reviewer must be able to give up on a clarification loop.

    Text the intake agent cannot parse comes back as another clarification, so
    with only a follow-up form the request could never be abandoned.
    """
    workflow = FakeWorkflow()
    app = configured_app(monkeypatch, tmp_path, workflow)
    app.session_state["last_state"] = {
        "final_status": "needs_information",
        "final_message": "A date is required.",
        "missing_information": ["proposed date"],
    }
    app.run(timeout=30)

    button_with_label(app, "Abandon this request and start over").click()
    app.run(timeout=30)

    assert workflow.start_calls == []
    assert app.session_state["last_state"] is None
    assert app.session_state["thread_id"] != "test-thread"
    # Back on a fresh intake form.
    assert app.title[0].value == "New treatment request"


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
    assert any("All checks passed." in item.value for item in app.success)


def test_streamlit_review_renders_full_workflow_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
    evidence: list[LabelChunk],
) -> None:
    """The review screen surfaces the state the old UI never rendered."""
    app = configured_app(monkeypatch, tmp_path, FakeWorkflow())
    app.session_state["awaiting_review"] = True
    app.session_state["last_state"] = {
        "plan": treatment_plan,
        "review": CriticDecision(
            verdict="fixable",
            explanation="The rate exceeds the label maximum.",
            issues=["Proposed rate is above the label maximum."],
        ),
        "rule_result": RuleEngineResult(
            checks=[
                RuleCheck(
                    rule_name="max_rate",
                    passed=False,
                    severity="hard_violation",
                    explanation="Proposed rate exceeds the label maximum.",
                ),
                RuleCheck(
                    rule_name="trait_compatibility",
                    passed=True,
                    severity="informational",
                    explanation="The field's trait package tolerates the product.",
                ),
            ],
            all_passed=False,
        ),
        "field_record": field_record,
        "product_record": product_record,
        "application_history": application_history,
        "weather": weather,
        "evidence": evidence,
        "revision_count": 2,
        "audit_log": ["Intake parsed.", "Rules evaluated."],
    }

    app.run(timeout=30)

    assert not app.exception

    warnings = [warning.value for warning in app.warning]
    assert any("Fixable issues" in value for value in warnings)

    markdown = [item.value for item in app.markdown]
    # The failing rule check, its severity, and the field record are all shown.
    assert any("Max rate" in value for value in markdown)
    assert any("1 of 2 checks did not pass" in value for value in markdown)
    assert any(field_record.growth_stage in value for value in markdown)
    # The retrieved passage itself, not just a citation string.
    assert any(evidence[0].text in value for value in markdown)

    captions = [caption.value for caption in app.caption]
    assert any("2 revisions" in value for value in captions)


def test_escalated_result_still_shows_evidence_and_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
) -> None:
    """An escalated run never reaches the review screen.

    Its evidence and rule results would otherwise be invisible, which is
    exactly the case where someone needs to see why it was escalated.
    """
    app = configured_app(monkeypatch, tmp_path, FakeWorkflow())
    app.session_state["last_state"] = {
        "final_status": "escalated",
        "final_message": "The request requires manual compliance review.",
        "plan": treatment_plan,
        "evidence": evidence,
        "rule_result": RuleEngineResult(
            checks=[
                RuleCheck(
                    rule_name="trait_compatibility",
                    passed=False,
                    severity="hard_violation",
                    explanation="The field's trait package is not on the label.",
                )
            ],
            all_passed=False,
        ),
        "audit_log": [
            "Intake selected the gather_context route.",
            "Request escalated.",
        ],
        "question": "Treat F-01 with Example Product.",
    }

    app.run(timeout=30)

    assert not app.exception

    markdown = [item.value for item in app.markdown]
    assert any(evidence[0].text in value for value in markdown)
    assert any("Trait compatibility" in value for value in markdown)
    assert any("Request escalated." in value for value in markdown)


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

    button_label = "Accept plan" if decision == "approved" else "Decline plan"
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
    button_with_label(app, "Start a new request").click()
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

    app = AppTest.from_file(QUEUE_PAGE_PATH).run(timeout=30)

    assert not app.exception
    table = app.dataframe[0].value
    assert result.work_order_id in list(table["work_order_id"])
    assert treatment_plan.product_name in list(table["product_name"])
