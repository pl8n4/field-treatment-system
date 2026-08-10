"""The deterministic rule engine's checks.

This is the evidence a reviewer is really being asked to sign off on: the rule
engine is code, not a model, so its verdicts are the reproducible part of the
recommendation. Failures sort to the top, worst severity first.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import formatting


def render(rule_result: dict[str, Any]) -> None:
    checks = rule_result.get("checks", []) or []
    if not checks:
        st.info("The rule engine did not report any checks for this plan.")
        return

    failed = [check for check in checks if not check.get("passed")]
    passed = [check for check in checks if check.get("passed")]

    if failed:
        st.markdown(f"**{len(failed)} of {len(checks)} checks did not pass**")
        for check in sorted(
            failed, key=lambda c: formatting.severity_rank(str(c.get("severity", "")))
        ):
            _render_check(check, passed=False)
    else:
        st.success(
            f"All {len(checks)} label and field checks passed.",
            icon=":material/check_circle:",
        )

    if passed:
        with st.expander(f"Checks that passed ({len(passed)})"):
            for check in passed:
                _render_check(check, passed=True)


def _render_check(check: dict[str, Any], *, passed: bool) -> None:
    severity = str(check.get("severity", ""))
    name = _humanise(str(check.get("rule_name", "Unnamed rule")))

    with st.container(border=True):
        heading, tag = st.columns([4, 1], vertical_alignment="center")
        heading.markdown(
            f"{':material/check_circle:' if passed else ':material/cancel:'} **{name}**"
        )
        if not passed:
            tag.badge(
                formatting.severity_label(severity),
                color=formatting.severity_color(severity),
            )
        explanation = check.get("explanation", "")
        if explanation:
            st.caption(explanation)


def _humanise(rule_name: str) -> str:
    """`max_rate_check` reads as a variable; `Max rate check` reads as a rule."""
    return rule_name.replace("_", " ").strip().capitalize()
