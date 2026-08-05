from typing import Any

import pytest
from langchain_core.documents import Document
from pydantic import ValidationError

import data_layer.retriever as retriever_module


class FakeRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.query: str | None = None

    def invoke(self, query: str) -> list[Document]:
        self.query = query
        return self.documents


class FakeStore:
    def __init__(self, documents: list[Document]) -> None:
        self.retriever = FakeRetriever(documents)
        self.search_type: str | None = None
        self.search_kwargs: dict[str, Any] | None = None

    def as_retriever(
        self,
        *,
        search_type: str,
        search_kwargs: dict[str, Any],
    ) -> FakeRetriever:
        self.search_type = search_type
        self.search_kwargs = search_kwargs
        return self.retriever


def label_document() -> Document:
    return Document(
        page_content="Do not apply when wind exceeds the label maximum.",
        metadata={
            "product": "Example Product",
            "epa_reg_no": "1-1",
            "page": 7,
            "source": "example-label.pdf",
        },
    )


def test_search_applies_product_filter_and_preserves_citation_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeStore([label_document()])
    monkeypatch.setattr(retriever_module, "vector_store", lambda: store)

    results = retriever_module.search(
        "wind restriction",
        product="Example Product",
        k=2,
        fetch_k=8,
        lambda_mult=0.25,
    )

    assert store.search_type == "mmr"
    assert store.search_kwargs == {
        "k": 2,
        "fetch_k": 8,
        "lambda_mult": 0.25,
        "filter": {"product": "Example Product"},
    }
    assert store.retriever.query == "wind restriction"
    assert len(results) == 1
    assert results[0].text == label_document().page_content
    assert results[0].source == "example-label.pdf"
    assert results[0].page == 7
    assert results[0].product == "Example Product"
    assert results[0].epa_reg_no == "1-1"


def test_search_without_product_does_not_add_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeStore([])
    monkeypatch.setattr(retriever_module, "vector_store", lambda: store)

    assert retriever_module.search("buffer") == []
    assert store.search_kwargs is not None
    assert "filter" not in store.search_kwargs


def test_chunk_ids_are_stable_and_unique() -> None:
    chunks = [label_document(), label_document()]

    assert retriever_module._chunk_ids(chunks) == [
        "1-1:p7:0",
        "1-1:p7:1",
    ]


def test_label_chunk_conversion_rejects_missing_metadata() -> None:
    document = Document(
        page_content="Incomplete evidence.",
        metadata={"product": "Example Product"},
    )

    with pytest.raises(ValidationError):
        retriever_module._to_label_chunk(document)
