from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from data_layer.records import DATA_DIR, list_products

"""
Reads each EPA-stamped PDF ({company}-{product}-{date}.pdf) in data/labels/,
cleans the extracted text, and splits it into overlapping chunks carrying their
corresponding product, registration number, and page.

Chunks overlap because label restrictions are the sentences most likely to
straddle a boundary, and half a restriction retrieves as a complete one.
"""

LABELS_DIR = DATA_DIR / "labels"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
MIN_PAGE_CHARACTERS = 100


def clean_page_text(text: str) -> str:
    """Repair what PDF text extraction breaks: null bytes, hyphenated line
    breaks, and the ragged whitespace of a two-column label layout.
    """
    text = text.replace("\x00", " ")
    # Rejoin a word split across lines by a hyphen: "applica-\ntion" -> "application"
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    # Collapse line breaks and runs of whitespace into single spaces
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_documents() -> list[Document]:
    """One cleaned Document per label page, citation metadata attached at load time."""
    product_names = {p.epa_reg_no: p.name for p in list_products()}
    documents: list[Document] = []
    for path in sorted(LABELS_DIR.glob("*.pdf")):
        company, product_code, _date = path.stem.split("-")
        reg_no = f"{int(company)}-{int(product_code)}"
        name = product_names[reg_no]  # unknown PDF -> loud KeyError, on purpose
        for page_no, page in enumerate(PdfReader(path).pages, start=1):
            text = clean_page_text(page.extract_text() or "")
            if len(text) < MIN_PAGE_CHARACTERS:
                continue  # blank pages and pages that are entirely artwork
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "product": name,
                        "epa_reg_no": reg_no,
                        "page": page_no,
                        "source": path.name,
                    },
                )
            )
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """Split pages into overlapping chunks. Each chunk inherits its page's metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
    )
    return splitter.split_documents(documents)


def load_chunks() -> list[Document]:
    """Every label PDF, cleaned and chunked, ready for the vector store."""
    return split_documents(load_documents())
