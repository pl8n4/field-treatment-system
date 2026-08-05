from typing import Any
from unittest.mock import Mock

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


def test_embeddings_uses_configured_model_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding_factory = Mock(return_value=object())
    monkeypatch.setattr(
        retriever_module,
        "HuggingFaceEmbeddings",
        embedding_factory,
    )
    retriever_module._embeddings.cache_clear()

    first = retriever_module._embeddings()
    second = retriever_module._embeddings()

    assert first is second
    embedding_factory.assert_called_once_with(
        model_name=retriever_module.EMBEDDING_MODEL_NAME
    )
    retriever_module._embeddings.cache_clear()


def test_connect_configures_persistent_chroma_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chroma = Mock(return_value=object())
    embedding = object()
    monkeypatch.setattr(retriever_module, "Chroma", chroma)
    monkeypatch.setattr(retriever_module, "_embeddings", lambda: embedding)

    retriever_module._connect()

    chroma.assert_called_once_with(
        collection_name=retriever_module.COLLECTION_NAME,
        embedding_function=embedding,
        persist_directory=str(retriever_module.CHROMA_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )


def test_ingest_adds_loaded_chunks_with_stable_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [label_document(), label_document()]
    store = Mock()
    monkeypatch.setattr(retriever_module, "load_chunks", lambda: chunks)

    count = retriever_module._ingest(store)

    assert count == 2
    store.add_documents.assert_called_once_with(
        chunks,
        ids=["1-1:p7:0", "1-1:p7:1"],
    )


@pytest.mark.parametrize("existing_ids", [[], ["existing-id"]])
def test_vector_store_ingests_only_when_collection_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    existing_ids: list[str],
) -> None:
    store = Mock()
    store.get.return_value = {"ids": existing_ids}
    ingest = Mock(return_value=1)
    monkeypatch.setattr(retriever_module, "_connect", lambda: store)
    monkeypatch.setattr(retriever_module, "_ingest", ingest)
    retriever_module.vector_store.cache_clear()

    assert retriever_module.vector_store() is store
    assert ingest.call_count == (0 if existing_ids else 1)
    retriever_module.vector_store.cache_clear()


def test_known_scopes_are_distinct_and_crop_filter_uses_compatible_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Mock()
    store.get.return_value = {
        "metadatas": [
            {"crop_scope": "general"},
            {"crop_scope": "soybean"},
            {"crop_scope": "corn+soybean"},
            {"crop_scope": "non-crop"},
            {"crop_scope": "soybean"},
            None,
        ]
    }
    monkeypatch.setattr(retriever_module, "vector_store", lambda: store)
    retriever_module._known_scopes.cache_clear()

    crop_filter = retriever_module._crop_filter("soybean")

    allowed = crop_filter["crop_scope"]["$in"]
    assert set(allowed) == {"general", "soybean", "corn+soybean"}
    retriever_module._known_scopes.cache_clear()


def test_search_combines_product_and_crop_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeStore([])
    crop_filter = {"crop_scope": {"$in": ["general", "soybean"]}}
    monkeypatch.setattr(retriever_module, "vector_store", lambda: store)
    monkeypatch.setattr(retriever_module, "_crop_filter", lambda crop: crop_filter)

    retriever_module.search(
        "application rate",
        product="Example Product",
        crop="soybean",
    )

    assert store.search_kwargs is not None
    assert store.search_kwargs["filter"] == {
        "$and": [
            {"product": "Example Product"},
            crop_filter,
        ]
    }


def test_rebuild_deletes_collection_clears_caches_and_returns_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_store = Mock()
    rebuilt_store = Mock()
    rebuilt_store.get.return_value = {"ids": ["one", "two"]}
    cached_vector_store = Mock(return_value=rebuilt_store)
    cached_vector_store.cache_clear = Mock()
    known_scopes = Mock()
    known_scopes.cache_clear = Mock()
    monkeypatch.setattr(retriever_module, "_connect", lambda: old_store)
    monkeypatch.setattr(retriever_module, "vector_store", cached_vector_store)
    monkeypatch.setattr(retriever_module, "_known_scopes", known_scopes)

    count = retriever_module.rebuild()

    assert count == 2
    old_store.delete_collection.assert_called_once_with()
    cached_vector_store.cache_clear.assert_called_once_with()
    known_scopes.cache_clear.assert_called_once_with()
