"""Presentation vocabulary: how workflow values are named and coloured.

The workflow speaks in snake_case status and verdict codes. Nothing here
changes meaning; it only decides the words and colours the user sees, so that
the same code never reads two different ways on two different screens.
"""

from __future__ import annotations

from typing import Literal

Tone = Literal["success", "warning", "error", "info"]

# The colour names st.badge and Streamlit's markdown colouring accept.
BadgeColor = Literal[
    "red",
    "orange",
    "yellow",
    "blue",
    "green",
    "violet",
    "gray",
    "grey",
    "primary",
]

# Terminal workflow statuses, from graph.py's terminal nodes.
STATUS_LABELS: dict[str, str] = {
    "simulated_work_order_created": "Approved — simulated work order created",
    "rejected": "Declined by reviewer",
    "escalated": "Escalated for manual compliance review",
    "needs_information": "More information needed",
    "failed": "Workflow could not complete",
}

STATUS_TONES: dict[str, Tone] = {
    "simulated_work_order_created": "success",
    "rejected": "warning",
    "escalated": "error",
    "needs_information": "info",
    "failed": "error",
}

STATUS_ICONS: dict[str, str] = {
    "simulated_work_order_created": ":material/task_alt:",
    "rejected": ":material/cancel:",
    "escalated": ":material/priority_high:",
    "needs_information": ":material/help:",
    "failed": ":material/error:",
}

# Critic verdicts, from workflow.schemas.CriticDecision.
VERDICT_LABELS: dict[str, str] = {
    "clean": "Clean",
    "fixable": "Fixable issues",
    "insufficient_info": "Insufficient information",
    "hard_violation": "Hard violation",
}

VERDICT_COLORS: dict[str, BadgeColor] = {
    "clean": "green",
    "fixable": "orange",
    "insufficient_info": "blue",
    "hard_violation": "red",
}

VERDICT_ICONS: dict[str, str] = {
    "clean": ":material/verified:",
    "fixable": ":material/build:",
    "insufficient_info": ":material/help:",
    "hard_violation": ":material/gpp_bad:",
}

# Rule-check severities, from workflow.schemas.RuleCheck.
SEVERITY_LABELS: dict[str, str] = {
    "hard_violation": "Hard violation",
    "fixable": "Fixable",
    "informational": "Informational",
}

SEVERITY_COLORS: dict[str, BadgeColor] = {
    "hard_violation": "red",
    "fixable": "orange",
    "informational": "blue",
}

# Worst first: a reviewer should meet the blocking checks before the notes.
SEVERITY_ORDER: dict[str, int] = {
    "hard_violation": 0,
    "fixable": 1,
    "informational": 2,
}


def status_label(status: str) -> str:
    """A sentence for a terminal status, falling back to the raw code."""
    return STATUS_LABELS.get(status, status.replace("_", " ").capitalize())


def status_tone(status: str) -> Tone:
    return STATUS_TONES.get(status, "info")


def status_icon(status: str) -> str:
    return STATUS_ICONS.get(status, ":material/info:")


def verdict_label(verdict: str) -> str:
    return VERDICT_LABELS.get(verdict, verdict.replace("_", " ").capitalize())


def verdict_color(verdict: str) -> BadgeColor:
    return VERDICT_COLORS.get(verdict, "gray")


def verdict_icon(verdict: str) -> str:
    return VERDICT_ICONS.get(verdict, ":material/help:")


def severity_label(severity: str) -> str:
    return SEVERITY_LABELS.get(severity, severity.replace("_", " ").capitalize())


def severity_color(severity: str) -> BadgeColor:
    return SEVERITY_COLORS.get(severity, "gray")


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get(severity, len(SEVERITY_ORDER))


def compass_point(degrees: float) -> str:
    """The 16-point compass name for a wind bearing in degrees."""
    points = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    return points[round(degrees / 22.5) % 16]


def optional(value: object, suffix: str = "") -> str:
    """Render a label limit, distinguishing "no limit set" from a value.

    A None limit on a ProductLimits field means the label sets no such
    restriction, which is a fact worth showing rather than a blank.
    """
    if value is None:
        return "No label limit"
    return f"{value}{suffix}"
