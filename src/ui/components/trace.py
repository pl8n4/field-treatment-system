"""The workflow trace, as a sequence of steps rather than a bullet list.

The audit log is the record of how a recommendation was reached, so it is worth
reading as a path: each entry gets its stage icon, a step number, and a colour
when it reports a failure or a decision.
"""

from __future__ import annotations

import streamlit as st

from ui.formatting import BadgeColor

# Matched against the audit-log text in order; the first hit wins. The phrases
# come from the audit_log entries written by graph.py's nodes.
STEP_STYLES: tuple[tuple[str, str, str, BadgeColor], ...] = (
    ("intake failed", "Intake", ":material/error:", "red"),
    ("intake selected", "Intake", ":material/input:", "primary"),
    ("paused for user information", "Clarification", ":material/pause_circle:", "blue"),
    ("context lookup", "Context", ":material/error:", "red"),
    ("context gathering failed", "Context", ":material/error:", "red"),
    ("requested acreage exceeded", "Context", ":material/warning:", "orange"),
    (
        "no requested or default application rate",
        "Context",
        ":material/warning:",
        "orange",
    ),
    ("weather unavailable", "Weather", ":material/cloud_off:", "orange"),
    ("loaded", "Context", ":material/inventory_2:", "primary"),
    ("retrieval failed", "Retrieval", ":material/error:", "red"),
    ("retrieved", "Retrieval", ":material/find_in_page:", "primary"),
    ("specialist failed", "Specialist", ":material/error:", "red"),
    ("specialist drafted", "Specialist", ":material/edit_document:", "primary"),
    ("rule engine failed", "Rules", ":material/error:", "red"),
    ("rule engine", "Rules", ":material/rule:", "primary"),
    ("critic failed", "Critic", ":material/error:", "red"),
    ("critic verdict agreed", "Critic", ":material/fact_check:", "green"),
    ("critic", "Critic", ":material/fact_check:", "primary"),
    ("human reviewer selected", "Human review", ":material/gavel:", "violet"),
    (
        "simulated work order created",
        "Work order",
        ":material/assignment_turned_in:",
        "green",
    ),
    ("rejected by human reviewer", "Outcome", ":material/cancel:", "orange"),
    ("escalated", "Outcome", ":material/priority_high:", "red"),
    ("controlled failure", "Outcome", ":material/error:", "red"),
)

DEFAULT_STYLE = ("Step", ":material/radio_button_checked:", "gray")


def _style(entry: str) -> tuple[str, str, str]:
    lowered = entry.lower()
    for phrase, stage, icon, color in STEP_STYLES:
        if phrase in lowered:
            return stage, icon, color
    return DEFAULT_STYLE


def render(entries: list[str], *, question: str = "") -> None:
    if not entries:
        st.caption("No workflow trace was recorded.")
        return

    st.caption(
        f"{len(entries)} steps, in the order the workflow took them. "
        "This is the record of how the recommendation was reached."
    )

    for number, entry in enumerate(entries, start=1):
        stage, icon, color = _style(entry)
        with st.container(border=True):
            marker, body = st.columns([1, 11], vertical_alignment="top")
            marker.markdown(f":{color}[{icon}]")
            body.markdown(f":{color}-badge[{stage}] &nbsp; **Step {number}**")
            body.markdown(entry)

    if question:
        with st.expander("The request as the workflow received it"):
            st.markdown(question)
