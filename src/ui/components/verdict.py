"""The critic's verdict, stated as a signal rather than a word in a sentence.

The verdict used to render as plain text, which made `hard_violation` and
`clean` look identical. Severity is the whole point of the field, so it is
encoded in colour, icon, and position.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import formatting


def render(
    review: dict[str, Any],
    rule_result: dict[str, Any],
    revision_count: int = 0,
) -> None:
    verdict = str(review.get("verdict", "unknown"))
    tone = {
        "clean": st.success,
        "fixable": st.warning,
        "insufficient_info": st.info,
        "hard_violation": st.error,
    }.get(verdict, st.info)

    checks = rule_result.get("checks", []) or []
    failed = [check for check in checks if not check.get("passed")]

    headline = (
        f"**{formatting.verdict_label(verdict)}** — {review.get('explanation', '')}"
    )
    tone(headline, icon=formatting.verdict_icon(verdict))

    summary_bits: list[str] = []
    if checks:
        summary_bits.append(
            f"{len(checks) - len(failed)} of {len(checks)} rules passed"
        )
    if revision_count:
        plural = "revision" if revision_count == 1 else "revisions"
        summary_bits.append(f"Plan rewritten after {revision_count} {plural}")
    if summary_bits:
        st.caption(" · ".join(summary_bits))

    for issue in review.get("issues", []) or []:
        st.markdown(f"- {issue}")
