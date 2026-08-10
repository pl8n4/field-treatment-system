"""The app's two destinations.

The review page is a single destination rather than three, because intake,
human review, and the result are one request moving through its stages — the
session state decides which stage the reviewer is looking at.
"""

from __future__ import annotations

import streamlit as st

from ui import shell
from ui.views import intake, queue, result, review


def review_page() -> None:
    if st.session_state.awaiting_review and st.session_state.last_state:
        shell.page_header(
            "Review recommendation",
            "Approve or decline the drafted treatment plan.",
        )
        review.render()
    elif st.session_state.last_state:
        shell.page_header("Request outcome", "What the workflow concluded.")
        result.render()
    else:
        shell.page_header(
            "New treatment request",
            "Describe the treatment; the workflow drafts a plan and checks it.",
        )
        intake.render()


def queue_page() -> None:
    shell.page_header(
        "Work orders",
        "Simulated records created by approved requests.",
    )
    queue.render()
