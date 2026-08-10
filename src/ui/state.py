"""Session bootstrap and workflow transitions.

Streamlit reruns the whole script on every interaction, so anything that must
survive a rerun lives in ``st.session_state`` and is created here exactly once.
"""

from __future__ import annotations

import uuid
from typing import Any

import streamlit as st

from workflow.graph import AgriculturalWorkflow


def new_thread_id() -> str:
    """A fresh LangGraph conversation thread id."""
    return str(uuid.uuid4())


def bootstrap() -> None:
    """Create the session objects every view depends on, once per session.

    Tests inject their own workflow before the first run, so each key is only
    filled when it is absent rather than overwritten.
    """
    if "workflow" not in st.session_state:
        st.session_state.workflow = AgriculturalWorkflow()
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = new_thread_id()
    if "awaiting_review" not in st.session_state:
        st.session_state.awaiting_review = False
    if "last_state" not in st.session_state:
        st.session_state.last_state = None


def save_workflow_state(state: dict[str, Any]) -> None:
    """Record a workflow return value and whether it paused for human review."""
    st.session_state.awaiting_review = bool(state.get("__interrupt__"))
    st.session_state.last_state = state


def start_new_request() -> None:
    """Clear the current result and open a fresh conversation thread."""
    st.session_state.last_state = None
    st.session_state.awaiting_review = False
    st.session_state.reviewer_note = ""
    st.session_state.thread_id = new_thread_id()


def as_dict(value: Any) -> dict[str, Any]:
    """Return workflow models and dictionaries in a display-friendly form.

    The workflow returns Pydantic models, but an interrupted run replays them
    from the checkpoint as plain dictionaries, so views must accept both.
    """
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def as_dicts(values: Any) -> list[dict[str, Any]]:
    """The same normalisation for a list of models, skipping anything unusable."""
    if not isinstance(values, (list, tuple)):
        return []
    return [item for item in (as_dict(value) for value in values) if item]
