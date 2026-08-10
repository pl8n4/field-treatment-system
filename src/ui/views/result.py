"""The terminal screen: what the workflow concluded, and what happens next."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import formatting, progress
from ui import state as session
from ui.components import (
    compliance,
    conditions,
    context,
    evidence,
    plan,
    trace,
)


def render() -> None:
    state = st.session_state.last_state
    workflow = st.session_state.workflow

    status = str(state.get("final_status", "unknown"))
    message = state.get("final_message", "")

    banner = {
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
        "info": st.info,
    }[formatting.status_tone(status)]
    banner(
        f"**{formatting.status_label(status)}**"
        + (f"\n\n{message}" if message else ""),
        icon=formatting.status_icon(status),
    )

    _render_error(state, status)
    _render_work_order(state)
    _render_reviewer_note()
    _render_missing_information(state)
    _render_traceability(state)

    st.divider()

    if status == "needs_information":
        _render_followup(workflow)
    elif st.button(
        "Start a new request",
        type="primary",
        icon=":material/add:",
    ):
        session.start_new_request()
        st.rerun()


def _render_error(state: dict[str, Any], status: str) -> None:
    """The workflow's own error text, which the old screen never showed.

    On a failure the message already carries it, so it is only worth adding
    when an error was recorded without ending the run in failure.
    """
    error = state.get("error")
    if error and status != "failed":
        st.error(f"The workflow reported: {error}", icon=":material/error:")


def _render_work_order(state: dict[str, Any]) -> None:
    work_order = session.as_dict(state.get("work_order"))
    if not work_order:
        return

    with st.container(border=True):
        st.caption("SIMULATED WORK ORDER")
        st.markdown(f"**{work_order.get('work_order_id')}**")
        st.caption(
            work_order.get("message")
            or "This is a simulated record. No real treatment was scheduled."
        )


def _render_reviewer_note() -> None:
    """The note the reviewer wrote with their decision.

    It belongs to this session only: the work-order record has no column for
    it, so the caption says so rather than implying it was filed.
    """
    note = st.session_state.get("reviewer_note", "")
    if not note:
        return

    with st.container(border=True):
        st.caption("YOUR REVIEW NOTE")
        st.markdown(note)
        st.caption(
            "Kept for this session only — it is not stored on the simulated "
            "work-order record."
        )


def _render_missing_information(state: dict[str, Any]) -> None:
    missing = state.get("missing_information") or []
    if not missing:
        return
    st.markdown("**The workflow still needs:**")
    for item in missing:
        st.markdown(f"- {item}")


def _render_traceability(state: dict[str, Any]) -> None:
    """Everything the run was based on, whatever outcome it reached.

    An escalated or rejected request never passes through the review screen, so
    without this its evidence and rule results would never be visible at all —
    which is precisely when someone needs to see why.
    """
    chunks = session.as_dicts(state.get("evidence"))
    steps = state.get("audit_log") or []
    rule_result = session.as_dict(state.get("rule_result"))
    treatment_plan = session.as_dict(state.get("plan"))
    field_record = session.as_dict(state.get("field_record"))
    product_record = session.as_dict(state.get("product_record"))
    history = session.as_dicts(state.get("application_history"))
    weather = session.as_dict(state.get("weather"))

    if not any([chunks, steps, rule_result, treatment_plan]):
        return

    st.subheader("Evidence and traceability", anchor=False)

    labels: list[str] = []
    renderers: list[Any] = []

    if chunks or treatment_plan.get("citations"):
        labels.append(f"Label evidence ({len(chunks)})" if chunks else "Label evidence")
        renderers.append(
            lambda: evidence.render(chunks, treatment_plan.get("citations") or [])
        )
    if rule_result:
        labels.append("Compliance checks")
        renderers.append(lambda: compliance.render(rule_result))
    if treatment_plan:
        labels.append("Drafted plan")
        renderers.append(lambda: _render_drafted_plan(treatment_plan))
    if weather or product_record:
        labels.append("Forecast conditions")
        renderers.append(lambda: conditions.render(weather, product_record))
    if field_record or product_record:
        labels.append("Field and label record")
        renderers.append(
            lambda: context.render(
                field_record, product_record, history, treatment_plan
            )
        )
    if steps:
        labels.append(f"Workflow trace ({len(steps)})")
        renderers.append(
            lambda: trace.render(steps, question=str(state.get("question") or ""))
        )

    # Labels and renderers are appended in lockstep; strict catches a mismatch.
    for tab, render_tab in zip(st.tabs(labels), renderers, strict=True):
        with tab:
            render_tab()


def _render_drafted_plan(treatment_plan: dict[str, Any]) -> None:
    """The plan as drafted, even when it was never approved."""
    plan.render_summary(treatment_plan)
    plan.render_narrative(treatment_plan)
    plan.render_assumptions(treatment_plan)


def _render_followup(workflow: object) -> None:
    """Collect the missing details and continue the same conversation thread.

    The abandon button is not optional. Anything the intake agent cannot parse
    comes back as another clarification, so without a way out a reviewer who
    wants to give up is asked for more information indefinitely.
    """
    st.subheader("Continue this request", anchor=False)
    with st.form("followup_form"):
        followup = st.text_area(
            "Follow-up response",
            placeholder="Provide the missing information to continue...",
            height=100,
        )
        followup_submitted = st.form_submit_button("Continue", type="primary")

    if st.button(
        "Abandon this request and start over",
        icon=":material/restart_alt:",
        help="Discards this conversation and opens a new, empty request.",
    ):
        session.start_new_request()
        st.rerun()

    if not followup_submitted:
        return

    if not followup.strip():
        st.warning("Please provide the missing information before continuing.")
        return

    with progress.WorkflowProgress("Continuing the treatment workflow...") as running:
        next_state = workflow.start(  # type: ignore[attr-defined]
            question=followup,
            thread_id=st.session_state.thread_id,
            on_node=running.record,
        )
    session.save_workflow_state(next_state)
    st.rerun()
