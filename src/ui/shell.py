"""The frame around every page: sidebar, identity, and run status.

Sidebar content is drawn in call order, so the identity block is rendered
before ``st.navigation`` and the session block after it.
"""

from __future__ import annotations

import streamlit as st

from workflow import config


def _provider_summary() -> str:
    """The model backing this session, so a reviewer knows what drafted a plan."""
    if config.MODEL_PROVIDER == "gemini":
        return f"Gemini · {config.GEMINI_MODEL}"
    return f"Ollama · {config.OLLAMA_MODEL}"


def render_identity() -> None:
    """The app name, above the navigation control."""
    with st.sidebar:
        st.markdown("### AgriFlow AI")
        st.caption("Field treatment review")


def render_session_panel() -> None:
    """Run status, the safety boundary, and session facts, below navigation."""
    with st.sidebar:
        st.divider()

        if st.session_state.get("awaiting_review"):
            st.warning("Awaiting your review", icon=":material/gavel:")
        elif st.session_state.get("last_state"):
            st.info("Request complete", icon=":material/check_circle:")

        with st.expander("Session details"):
            st.caption(f"Model: {_provider_summary()}")
            thread_id = st.session_state.get("thread_id", "")
            if thread_id:
                st.caption(f"Thread: `{thread_id[:8]}`")


def page_header(title: str, subtitle: str) -> None:
    """A consistent heading for a page, so every screen opens the same way.

    ``anchor=False`` drops Streamlit's automatic heading link, which is for
    deep-linking into long documents and only adds clutter here.
    """
    st.title(title, anchor=False)
    st.caption(subtitle)
