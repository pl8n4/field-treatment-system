"""Pull the cited page out of an EPA label PDF.

``st.pdf`` has no page parameter and these labels run to 171 pages, so opening
one at page 1 for a page-58 citation would show the reviewer nothing. Instead
the cited page is extracted into a one-page document, which makes the embedded
file itself the citation.

A chunk never spans a page break — corpus.scope_chunks resets its context at
one — so a single page always contains the whole passage.
"""

from __future__ import annotations

import io
from pathlib import Path

import streamlit as st
from pypdf import PdfReader, PdfWriter

from data_layer.corpus import LABELS_DIR, clean_page_text


def label_path(source: str) -> Path | None:
    """Resolve a citation's filename inside the labels directory, or None.

    ``Path(source).name`` keeps a stored filename from escaping the directory.
    """
    if not source:
        return None
    path = LABELS_DIR / Path(source).name
    return path if path.is_file() else None


@st.cache_data(show_spinner=False)
def cited_page(source: str, page: int) -> bytes | None:
    """The cited page as a standalone one-page PDF, or None if unavailable.

    Cached because Streamlit reruns the script on every interaction and this
    would otherwise re-parse the label each time.
    """
    path = label_path(source)
    if path is None:
        return None

    reader = PdfReader(str(path))
    if not 1 <= page <= len(reader.pages):
        return None

    writer = PdfWriter()
    writer.add_page(reader.pages[page - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@st.cache_data(show_spinner=False)
def page_text(source: str, page: int) -> str | None:
    """The whole cited page as text, for reading around a retrieved passage.

    Cleaned the same way the corpus cleans it, so what a reviewer reads here
    matches what was chunked and indexed.
    """
    path = label_path(source)
    if path is None:
        return None

    reader = PdfReader(str(path))
    if not 1 <= page <= len(reader.pages):
        return None

    return clean_page_text(reader.pages[page - 1].extract_text() or "")


@st.cache_data(show_spinner=False)
def full_label(source: str) -> bytes | None:
    """The complete label, for download. Read only when a reviewer asks."""
    path = label_path(source)
    return path.read_bytes() if path is not None else None


@st.cache_data(show_spinner=False)
def page_count(source: str) -> int | None:
    path = label_path(source)
    return len(PdfReader(str(path)).pages) if path is not None else None
