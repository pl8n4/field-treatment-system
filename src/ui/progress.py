"""Live progress for a workflow run.

A single spinner for a nine-node chain of model calls tells a user nothing
about whether anything is happening. The workflow reports each node as it
completes, and this turns those node names into stage labels.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import streamlit as st

# Node names from graph.py's add_node calls.
STAGE_LABELS: dict[str, str] = {
    "intake": "Reading the request",
    "clarify": "Identifying missing information",
    "gather_context": "Loading field, product, and weather records",
    "retrieve": "Retrieving product-label evidence",
    "specialist": "Drafting the treatment plan",
    "rules": "Running deterministic compliance rules",
    "critic": "Reviewing the plan against its evidence",
    "human_review": "Preparing the plan for your review",
    "write_work_order": "Creating the simulated work order",
    "rejected": "Recording the rejection",
    "escalate": "Escalating for manual review",
    "failure": "Ending in a controlled failure",
}


def stage_label(node_name: str) -> str:
    return STAGE_LABELS.get(node_name, node_name.replace("_", " ").capitalize())


class WorkflowProgress:
    """A status box that names each stage as the workflow finishes it."""

    def __init__(self, label: str = "Running the treatment workflow...") -> None:
        self._label = label
        self._status: Any = None
        self._completed: list[str] = []

    def __enter__(self) -> WorkflowProgress:
        self._status = st.status(self._label, expanded=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._status is None:
            return
        if exc_type is not None:
            self._status.update(label="The workflow did not complete.", state="error")
        else:
            self._status.update(
                label="Workflow complete", state="complete", expanded=False
            )

    def record(self, node_name: str) -> None:
        """Mark a node as finished. Passed to the workflow as its callback."""
        if self._status is None:
            return
        label = stage_label(node_name)
        self._completed.append(label)
        self._status.write(f"✓ {label}")
        self._status.update(label=label)
