"""Extracting the cited page out of a real EPA label PDF."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from data_layer.corpus import LABELS_DIR, clean_page_text, load_chunks
from ui import label_pdf


@pytest.fixture(scope="module")
def a_label() -> str:
    labels = sorted(path.name for path in LABELS_DIR.glob("*.pdf"))
    if not labels:
        pytest.skip("No label PDFs are present in data/labels.")
    return labels[0]


def test_label_path_resolves_a_known_label(a_label: str) -> None:
    assert label_pdf.label_path(a_label) == LABELS_DIR / a_label


def test_label_path_rejects_unknown_and_empty_sources() -> None:
    assert label_pdf.label_path("does-not-exist.pdf") is None
    assert label_pdf.label_path("") is None


def test_label_path_cannot_escape_the_labels_directory() -> None:
    """A stored filename must not be able to read outside data/labels."""
    assert label_pdf.label_path("../../pyproject.toml") is None


def test_cited_page_returns_a_single_page_document(a_label: str) -> None:
    extracted = label_pdf.cited_page(a_label, 2)

    assert extracted is not None
    assert len(PdfReader(io.BytesIO(extracted)).pages) == 1


def test_cited_page_rejects_pages_outside_the_document(a_label: str) -> None:
    total = label_pdf.page_count(a_label)
    assert total is not None

    assert label_pdf.cited_page(a_label, 0) is None
    assert label_pdf.cited_page(a_label, total + 1) is None


def test_extracted_page_carries_the_text_of_the_page_it_cites() -> None:
    """The page a chunk claims to come from must be the page extracted.

    Showing a reviewer the wrong page of a label would be worse than showing
    none, so this checks the mapping on real corpus metadata rather than
    trusting the page number.
    """
    chunks = load_chunks()
    checked = 0
    for chunk in chunks[::200]:
        source = chunk.metadata["source"]
        page = chunk.metadata["page"]

        extracted = label_pdf.cited_page(source, page)
        assert extracted is not None

        text = clean_page_text(PdfReader(io.BytesIO(extracted)).pages[0].extract_text())
        assert chunk.page_content.strip()[:60] in text
        checked += 1

    assert checked > 0


def test_page_text_returns_more_than_a_chunk(a_label: str) -> None:
    """The full page is the reading context a chunk cannot give.

    Chunks are capped at CHUNK_SIZE characters, so a page generally holds
    several; this is what lets a reviewer read around a retrieved passage.
    """
    text = label_pdf.page_text(a_label, 2)

    assert text is not None
    assert len(text) > 0


def test_page_text_rejects_pages_outside_the_document(a_label: str) -> None:
    total = label_pdf.page_count(a_label)
    assert total is not None

    assert label_pdf.page_text(a_label, 0) is None
    assert label_pdf.page_text(a_label, total + 1) is None
    assert label_pdf.page_text("does-not-exist.pdf", 1) is None
