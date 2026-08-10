"""Label evidence, down to the page it came from.

Rendered from ``state["evidence"]`` — the retriever's own LabelChunk records —
rather than from the plan's citation strings, which the model writes as free
text. The chunk text shown here is exactly what the specialist and critic were
given, and the embedded page is the source it was cut from.
"""

from __future__ import annotations

from typing import Any

import streamlit as st
from streamlit.errors import StreamlitAPIException

from ui import label_pdf

PDF_VIEWER_HEIGHT = 700


def render(evidence: list[dict[str, Any]], citations: list[str]) -> None:
    if not evidence:
        _render_citation_fallback(citations)
        return

    st.caption(
        f"{len(evidence)} passage(s) retrieved from the product label and supplied "
        "to the specialist and the critic."
    )
    for index, chunk in enumerate(evidence):
        _render_chunk(chunk, index)


def _render_chunk(chunk: dict[str, Any], index: int) -> None:
    source = str(chunk.get("source", ""))
    page = chunk.get("page")
    product = chunk.get("product", "Unknown product")
    section = chunk.get("section") or chunk.get("part") or ""

    header = f"{product} — {source}"
    if page is not None:
        header += f", page {page}"

    with st.expander(header):
        if section:
            st.caption(section)

        st.markdown("**Retrieved passage**")
        st.caption("The exact text the specialist and critic were given.")
        st.markdown(f"> {str(chunk.get('text', '')).strip()}")

        if not source or page is None:
            return
        if label_pdf.label_path(source) is None:
            st.caption("The source PDF is not available in this installation.")
            return

        _render_page_text(source, int(page), index)
        _render_source_page(source, int(page), index)


def _render_page_text(source: str, page: int, index: int) -> None:
    """The whole page around the passage, for reading a fuller section.

    Retrieved chunks are about 900 characters, which is often a paragraph or
    two — enough for the model, but less than a person reading for context
    usually wants. This is explicitly labelled as text the model did not see,
    so the passage above stays an accurate record of the evidence.
    """
    text = label_pdf.page_text(source, page)
    if not text:
        return

    if not st.toggle(
        f"Read the full page text ({len(text):,} characters)",
        key=f"evidence_text_{index}_{source}_{page}",
    ):
        return

    st.caption(
        "Surrounding context from the same page. This was **not** part of the "
        "evidence the model was given."
    )
    with st.container(height=320, border=True):
        st.markdown(text)


def _render_source_page(source: str, page: int, index: int) -> None:
    """The cited page itself, loaded only when a reviewer asks for it.

    Streamlit reruns the whole script on every interaction, so several PDF
    viewers rendering at once is real weight in the browser; the toggle keeps
    them off the page until they are wanted.
    """
    total = label_pdf.page_count(source)
    label = f"Show page {page}" + (f" of {total}" if total else "")

    if not st.toggle(label, key=f"evidence_pdf_{index}_{source}_{page}"):
        return

    page_bytes = label_pdf.cited_page(source, page)
    if page_bytes is None:
        st.caption(f"Page {page} could not be read from {source}.")
        return

    try:
        st.pdf(page_bytes, height=PDF_VIEWER_HEIGHT)
    except (ImportError, StreamlitAPIException):
        # st.pdf needs the streamlit-pdf extra; the passage above is still the
        # evidence, so a missing viewer degrades to the downloadable source.
        st.caption("The PDF viewer is unavailable. Download the label instead.")

    full = label_pdf.full_label(source)
    if full is not None:
        st.download_button(
            "Download the full label",
            data=full,
            file_name=source,
            mime="application/pdf",
            key=f"evidence_download_{index}_{source}_{page}",
        )


def _render_citation_fallback(citations: list[str]) -> None:
    """With no retrieved chunks, show whatever the plan claimed to cite."""
    if not citations:
        st.info("No label evidence was retrieved for this request.")
        return
    st.caption(
        "No label passages were recorded for this run. The plan cited the "
        "following sources:"
    )
    for citation in citations:
        st.markdown(f"- {citation}")
