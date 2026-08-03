"""Build the vector store and perform semantic search on it.

Results are re-ranked with maximal marginal relevance (MMR).

Run `python -m data_layer.retriever` to force a rebuild after changing data/labels/.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from data_layer.corpus import load_chunks
from data_layer.records import DATA_DIR
from data_layer.schemas import LabelChunk

CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION_NAME = "labels"

# The same model has to embed both the documents and the queries.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# MMR fetches fetch_k by similarity, then returns the k least redundant of them.
# lambda_mult trades relevance to the query (1.0) against diversity (0.0).
DEFAULT_K = 4
DEFAULT_FETCH_K = 20
DEFAULT_LAMBDA_MULT = 0.5


@lru_cache(maxsize=1)
def _embeddings() -> HuggingFaceEmbeddings:
    """The embedding model, loaded once per process."""
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)


def _connect() -> Chroma:
    """Open the persistent collection without ingesting anything."""
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )


def _chunk_ids(chunks: list[Document]) -> list[str]:
    """Stable ids, so re-ingesting the same corpus updates rows instead of duplicating them."""
    return [
        f"{c.metadata['epa_reg_no']}:p{c.metadata['page']}:{i}"
        for i, c in enumerate(chunks)
    ]


def _ingest(store: Chroma) -> int:
    """Embed the corpus into the store. Returns the chunk count."""
    chunks = load_chunks()
    store.add_documents(chunks, ids=_chunk_ids(chunks))
    return len(chunks)


@lru_cache(maxsize=1)
def vector_store() -> Chroma:
    """The label collection, ingested from the corpus on first use."""
    store = _connect()
    if not store.get(limit=1)["ids"]:
        _ingest(store)
    return store


def rebuild() -> int:
    """Drop the store and re-ingest data/labels/. Returns the chunk count."""
    _connect().delete_collection()
    vector_store.cache_clear()
    return len(vector_store().get()["ids"])


def search(
    query: str,
    *,
    product: str | None = None,
    k: int = DEFAULT_K,
    fetch_k: int = DEFAULT_FETCH_K,
    lambda_mult: float = DEFAULT_LAMBDA_MULT,
) -> list[LabelChunk]:
    """The k most relevant, mutually non-redundant chunks, optionally for one product.

    The product filter is the point of the metadata: a temperature restriction
    is looked up in one product's label, not across all five.
    """
    search_kwargs: dict = {"k": k, "fetch_k": fetch_k, "lambda_mult": lambda_mult}
    if product:
        search_kwargs["filter"] = {"product": product}

    retriever = vector_store().as_retriever(
        search_type="mmr", search_kwargs=search_kwargs
    )
    return [_to_label_chunk(document) for document in retriever.invoke(query)]


def _to_label_chunk(document: Document) -> LabelChunk:
    """Vector-store Document -> the domain type everything downstream cites."""
    return LabelChunk.model_validate(
        {"text": document.page_content, **document.metadata}
    )


if __name__ == "__main__":
    print(f"Ingested {rebuild()} chunks into {CHROMA_DIR}")
