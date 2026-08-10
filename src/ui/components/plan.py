"""The drafted treatment plan: what is actually being approved."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.components import facts


def render_summary(plan: dict[str, Any]) -> None:
    """The five facts that define the application, as a scannable row."""
    if not plan:
        st.info("No treatment plan was drafted.")
        return

    facts.grid(
        [
            ("Field", plan.get("field_id", "—")),
            ("Product", plan.get("product_name", "—")),
            ("Treatment date", str(plan.get("treatment_date", "—"))),
            ("Application rate", f"{plan.get('proposed_rate', '—')} fl oz/acre"),
            ("Treated area", f"{plan.get('treated_acres', '—')} acres"),
        ],
        per_row=3,
    )


def render_narrative(plan: dict[str, Any]) -> None:
    """The specialist's own account of timing, drift, and re-entry intervals."""
    sections = (
        ("Timing", plan.get("timing_summary", "")),
        ("Buffer and drift", plan.get("buffer_summary", "")),
        ("Restricted-entry interval", plan.get("rei_summary", "")),
        ("Pre-harvest interval", plan.get("phi_summary", "")),
    )
    for heading, body in sections:
        if body:
            st.markdown(f"**{heading}**")
            st.markdown(body)


def render_assumptions(plan: dict[str, Any]) -> None:
    """What the plan filled in for itself, which is where quiet errors hide."""
    assumptions = plan.get("assumptions") or []
    if not assumptions:
        return
    st.markdown("**Assumptions the plan relied on**")
    for assumption in assumptions:
        st.markdown(f"- {assumption}")
