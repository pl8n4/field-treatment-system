"""The human-review screen: the plan, its evidence, and the accept/decline gate.

Ordered the way a decision gets made: the verdict first, then what is being
approved, then the deterministic checks behind it, then the supporting record,
and only at the end the buttons that commit to it.
"""

from __future__ import annotations

import streamlit as st

from ui import state as session
from ui.components import (
    compliance,
    conditions,
    context,
    evidence,
    plan,
    trace,
    verdict,
)


def render() -> None:
    state = st.session_state.last_state
    workflow = st.session_state.workflow

    treatment_plan = session.as_dict(state.get("plan"))
    review = session.as_dict(state.get("review"))
    rule_result = session.as_dict(state.get("rule_result"))
    weather = session.as_dict(state.get("weather"))
    field_record = session.as_dict(state.get("field_record"))
    product_record = session.as_dict(state.get("product_record"))
    history = session.as_dicts(state.get("application_history"))
    chunks = session.as_dicts(state.get("evidence"))

    verdict.render(review, rule_result, int(state.get("revision_count", 0) or 0))

    st.subheader("Proposed application", anchor=False)
    plan.render_summary(treatment_plan)

    st.subheader("Compliance checks", anchor=False)
    compliance.render(rule_result)

    evidence_tab = f"Label evidence ({len(chunks)})" if chunks else "Label evidence"
    steps = state.get("audit_log") or []
    trace_tab = f"Workflow trace ({len(steps)})" if steps else "Workflow trace"

    detail_tabs = st.tabs(
        [
            evidence_tab,
            "Specialist notes",
            "Forecast conditions",
            "Field and label record",
            trace_tab,
        ]
    )
    with detail_tabs[0]:
        evidence.render(chunks, treatment_plan.get("citations") or [])
    with detail_tabs[1]:
        plan.render_narrative(treatment_plan)
        plan.render_assumptions(treatment_plan)
    with detail_tabs[2]:
        conditions.render(weather, product_record)
    with detail_tabs[3]:
        context.render(field_record, product_record, history, treatment_plan)
    with detail_tabs[4]:
        trace.render(steps, question=str(state.get("question") or ""))

    st.divider()
    _render_decision(workflow)


def _render_decision(workflow: object) -> None:
    st.subheader("Your decision", anchor=False)
    st.caption(
        "Accepting creates a simulated work-order record only. Nothing here "
        "schedules a real application."
    )

    note = st.text_area(
        "Reviewer note (optional)",
        placeholder="Why you are accepting or declining, for the record.",
        height=80,
    )

    accept_column, decline_column = st.columns(2)
    with accept_column:
        if st.button(
            "Accept plan",
            type="primary",
            width="stretch",
            icon=":material/check:",
        ):
            _resolve(workflow, "approved", "Recording acceptance...", note)
    with decline_column:
        if st.button(
            "Decline plan",
            width="stretch",
            icon=":material/close:",
        ):
            _resolve(workflow, "rejected", "Recording decline...", note)


def _resolve(
    workflow: object,
    decision: str,
    spinner_text: str,
    note: str,
) -> None:
    """Send the reviewer's decision, then open a fresh thread for the next one."""
    with st.spinner(spinner_text):
        result = workflow.resume_human_review(  # type: ignore[attr-defined]
            decision=decision,
            thread_id=st.session_state.thread_id,
        )
    st.session_state.awaiting_review = False
    st.session_state.last_state = result
    st.session_state.reviewer_note = note.strip()
    st.session_state.thread_id = session.new_thread_id()
    st.rerun()
