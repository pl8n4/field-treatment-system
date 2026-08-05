from pathlib import Path
from unittest.mock import Mock

import pytest
from langchain_core.documents import Document

import data_layer.corpus as corpus
from data_layer.schemas import ProductLimits


class FakePage:
    def __init__(self, text: str | None) -> None:
        self.text = text

    def extract_text(self) -> str | None:
        return self.text


class FakeReader:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages


def document(text: str, *, page: int = 1) -> Document:
    return Document(
        page_content=text,
        metadata={
            "product": "Example Product",
            "epa_reg_no": "1-1",
            "page": page,
            "source": "1-1-2026.pdf",
            "part": "",
            "section": "",
        },
    )


def test_clean_page_text_repairs_pdf_artifacts_and_preserves_paragraphs() -> None:
    raw = "Applica-\n tion\x00 instructions\n with   spacing.\n\nSecond paragraph."

    cleaned = corpus.clean_page_text(raw)

    assert cleaned == ("Application instructions with spacing.\n\nSecond paragraph.")


@pytest.mark.parametrize(
    ("scope", "crop", "expected"),
    [
        (corpus.GENERAL_SCOPE, "soybean", True),
        (corpus.NON_CROP_SCOPE, "soybean", False),
        ("corn+soybean", "soybean", True),
        ("corn+wheat", "soybean", False),
    ],
)
def test_scope_covers_expected_crops(
    scope: str,
    crop: str,
    expected: bool,
) -> None:
    assert corpus.scope_covers(scope, crop) is expected


def test_scope_chunks_inherits_crop_within_page_and_resets_at_page_break() -> None:
    chunks = [
        document("SOYBEAN application directions", page=1),
        document("Apply 32 fluid ounces per acre.", page=1),
        document("Apply only at the labeled rate.", page=2),
    ]

    scoped = corpus.scope_chunks(chunks)

    assert [chunk.metadata["crop_scope"] for chunk in scoped] == [
        "soybean",
        "soybean",
        corpus.GENERAL_SCOPE,
    ]


def test_scope_chunks_keeps_global_topic_general() -> None:
    chunks = [
        document("SOYBEAN application directions"),
        document("SPRAY DRIFT: Do not apply above the maximum wind speed."),
    ]

    scoped = corpus.scope_chunks(chunks)

    assert scoped[1].metadata["crop_scope"] == corpus.GENERAL_SCOPE


def test_crop_scope_rejects_non_crop_part() -> None:
    assert (
        corpus.crop_scope(
            "Soybean appears in this unrelated text.",
            part="II. INDUSTRIAL TURF AND ORNAMENTAL USES",
        )
        == corpus.NON_CROP_SCOPE
    )


def test_headings_ignore_blank_lines_and_capture_part_and_section() -> None:
    part, section = corpus._headings(
        "\nI. DIRECTIONS FOR USE WITH FOOD AND FEED CROPS\n\nSOYBEAN\n"
    )

    assert part == "I. DIRECTIONS FOR USE WITH FOOD AND FEED CROPS"
    assert section == "SOYBEAN"


def test_split_documents_preserves_metadata_and_strips_leading_punctuation() -> None:
    source = document(". " + ("Soybean application direction. " * 50))

    chunks = corpus.split_documents([source])

    assert chunks
    assert all(chunk.metadata["source"] == "1-1-2026.pdf" for chunk in chunks)
    assert all(not chunk.page_content.startswith(".") for chunk in chunks)
    assert all("crop_scope" in chunk.metadata for chunk in chunks)


def test_load_documents_skips_front_matter_and_short_pages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    label_path = tmp_path / "1-1-2026.pdf"
    label_path.touch()
    body = "I. DIRECTIONS FOR USE WITH FOOD AND FEED CROPS\nSOYBEAN\n" + (
        "application directions for soybean fields " * 5
    )
    reader = FakeReader(
        [
            FakePage("EPA approval letter\nSincerely"),
            FakePage("artwork"),
            FakePage(body),
        ]
    )
    monkeypatch.setattr(corpus, "LABELS_DIR", tmp_path)
    monkeypatch.setattr(corpus, "PdfReader", lambda path: reader)
    monkeypatch.setattr(
        corpus,
        "list_products",
        lambda: [ProductLimits(name="Example Product", epa_reg_no="1-1")],
    )

    documents = corpus.load_documents()

    assert len(documents) == 1
    assert documents[0].metadata["page"] == 3
    assert documents[0].metadata["source"] == label_path.name
    assert documents[0].metadata["product"] == "Example Product"
    assert documents[0].metadata["epa_reg_no"] == "1-1"
    assert documents[0].metadata["part"].startswith("I. DIRECTIONS")
    assert documents[0].metadata["section"] == "SOYBEAN"


def test_load_chunks_combines_document_loading_and_splitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [document("source")]
    chunks = [document("chunk")]
    monkeypatch.setattr(corpus, "load_documents", lambda: documents)
    split = Mock(return_value=chunks)
    monkeypatch.setattr(corpus, "split_documents", split)

    assert corpus.load_chunks() == chunks
    split.assert_called_once_with(documents)
