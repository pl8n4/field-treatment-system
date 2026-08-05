"""Reads each EPA-stamped PDF ({company}-{product}-{date}.pdf) in data/labels/,
cleans the extracted text, and splits it into overlapping chunks carrying their
corresponding product, registration number, page, and structural position.

Chunks overlap because label restrictions are the sentences most likely to
straddle a boundary, and half a restriction retrieves as a complete one.

The `part` and `crop_scope` tags matter: 116-167 of the Roundup master label's
171 pages are turf sites, and a turf rate cited for soybean looks plausible. So
does a cotton rate, which is why scope follows the crop heading a chunk sits
under and not only the words the chunk happens to contain.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from data_layer.records import DATA_DIR, list_products

LABELS_DIR = DATA_DIR / "labels"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
MIN_PAGE_CHARACTERS = 100

# The EPA approval letter opening every PPLS download is not the label, and
# must never be citable. It signs off on page 2 of all five current PDFs.
FRONT_MATTER_MARKER = "Sincerely"
FRONT_MATTER_SEARCH_PAGES = 10

# "I. DIRECTIONS FOR USE WITH FOOD AND FEED CROPS" — running header on every
# page of a master label's top-level division.
PART_PATTERN = re.compile(r"^([IVX]{1,5}\.\s+[A-Z][A-Z ,&'\-]{6,80})\s*$")

# "7.5 Surfactants", "3.0 PRECAUTIONARY STATEMENTS"
NUMBERED_SECTION_PATTERN = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+\s+\S.{2,70})\s*$")

# "SPECIFIC CROP DIRECTIONS", "APPENDIX 2", "SOYBEAN"
CAPS_SECTION_PATTERN = re.compile(r"^([A-Z][A-Z0-9 ,()/&'\-]{4,60})\s*$")

NON_CROP_PART_PATTERN = re.compile(r"INDUSTRIAL|TURF|ORNAMENTAL", re.IGNORECASE)

# Topics that are about the product rather than the crop it lands on. They stay
# "general" even under a crop heading, because they hold for every crop and a
# soybean plan must be able to cite them. Enlist prints its nozzle and boom
# height limits directly below the list of drift-susceptible crops, which would
# otherwise scope a product-wide drift restriction to cotton.
GLOBAL_TOPIC_PATTERN = re.compile(
    r"storage and disposal|pesticide storage|container handling"
    r"|refillable container|rinsate"
    r"|first aid|hazards to humans|environmental hazards"
    r"|personal protective|protective equipment"
    r"|restricted[- ]entry|re-?entry interval|early entry"
    r"|spray drift|susceptible plant|wind speed"
    r"|nozzle|groundboom|boom height|droplet"
    r"|ammonium sulfate|mixing order",
    re.IGNORECASE,
)

NON_CROP_SCOPE = "non-crop"
GENERAL_SCOPE = "general"
SCOPE_SEPARATOR = "+"

# Keys match products.json and fields.json, so a scope compares to FarmField.crop.
CROP_PATTERNS: dict[str, re.Pattern[str]] = {
    "alfalfa": re.compile(r"\balfalfa\b", re.IGNORECASE),
    "canola": re.compile(r"\bcanola\b", re.IGNORECASE),
    "corn": re.compile(r"\bcorn\b", re.IGNORECASE),
    "cotton": re.compile(r"\bcotton\b", re.IGNORECASE),
    "peanut": re.compile(r"\bpeanuts?\b", re.IGNORECASE),
    "potato": re.compile(r"\bpotato(?:es)?\b", re.IGNORECASE),
    "rice": re.compile(r"\brice\b", re.IGNORECASE),
    "safflower": re.compile(r"\bsafflowers?\b", re.IGNORECASE),
    "sorghum": re.compile(r"\bsorghum\b", re.IGNORECASE),
    "soybean": re.compile(r"\bsoybeans?\b", re.IGNORECASE),
    "sugar beet": re.compile(r"\bsugar\s?beets?\b", re.IGNORECASE),
    "sugarcane": re.compile(r"\bsugar\s?cane\b", re.IGNORECASE),
    "sunflower": re.compile(r"\bsunflowers?\b", re.IGNORECASE),
    "wheat": re.compile(r"\bwheat\b", re.IGNORECASE),
}


def clean_page_text(text: str) -> str:
    """Repair what PDF text extraction breaks: null bytes, hyphenated line
    breaks, and the ragged whitespace of a two-column label layout.
    """
    text = text.replace("\x00", " ")
    # Rejoin a word split across one line break: "applica-\ntion" -> "application"
    text = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", text)
    # Preserve blank-line-separated paragraphs while normalizing each paragraph.
    paragraphs = re.split(r"\n[ \t\r\f\v]*\n(?:[ \t\r\f\v]*\n)*", text)
    return "\n\n".join(
        normalized
        for paragraph in paragraphs
        if (normalized := re.sub(r"\s+", " ", paragraph).strip())
    )


def _front_matter_pages(reader: PdfReader) -> int:
    """Leading pages that are the EPA approval letter, not the label. Returns 0
    when no signature is found, so an odd PDF stays indexed rather than truncated.
    """
    last_signature = 0
    for page_no, page in enumerate(reader.pages[:FRONT_MATTER_SEARCH_PAGES], start=1):
        if FRONT_MATTER_MARKER in (page.extract_text() or ""):
            last_signature = page_no
    return last_signature


def _headings(raw_text: str) -> tuple[str | None, str | None]:
    """The last part and section heading on one page. Best-effort: a contents
    page yields a run and the last wins, which is harmless — no rule reads it.
    """
    part: str | None = None
    section: str | None = None

    for line in raw_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        if match := PART_PATTERN.match(stripped):
            part = match.group(1).strip()
            continue

        for pattern in (NUMBERED_SECTION_PATTERN, CAPS_SECTION_PATTERN):
            if match := pattern.match(stripped):
                section = match.group(1).strip()
                break

    return part, section


def crop_scope(text: str, *, part: str | None = None) -> str:
    """Crops this text names: "non-crop" under a turf part, "general" when it
    names none, else the names joined by "+". "general" is permissive on purpose
    — a wind rule names no crop and applies to all of them. Text alone is not
    enough to scope a chunk; `scope_chunks` reads it in the order it was printed.
    """
    if part and NON_CROP_PART_PATTERN.search(part):
        return NON_CROP_SCOPE

    named = sorted(
        crop for crop, pattern in CROP_PATTERNS.items() if pattern.search(text)
    )
    return SCOPE_SEPARATOR.join(named) if named else GENERAL_SCOPE


def scope_chunks(chunks: list[Document]) -> list[Document]:
    """Tag each chunk with the crops it may be cited for.

    A chunk that names no crop is governed by the crop named above it on the
    same page. That is how directions read: a crop heading, then the rates and
    intervals under it, which never repeat the name. Scoping a chunk on its own
    900 characters leaves Delaro's 35-day wheat pre-harvest interval citable as
    a soybean restriction, because the word "wheat" is a few lines further up.

    The context resets at the page break. Carrying a crop across pages swallows
    whole product-wide sections that happen to follow a crop section, and losing
    a storage or re-entry restriction is its own kind of wrong answer.
    """
    governing: str | None = None
    page: tuple[str, int] | None = None

    for chunk in chunks:
        here = (chunk.metadata["source"], chunk.metadata["page"])
        if here != page:
            governing = None
            page = here

        scope = crop_scope(
            chunk.page_content,
            part=chunk.metadata.get("part") or None,
        )

        if scope not in (GENERAL_SCOPE, NON_CROP_SCOPE):
            governing = scope
        elif (
            scope == GENERAL_SCOPE
            and governing
            and not GLOBAL_TOPIC_PATTERN.search(chunk.page_content)
        ):
            scope = governing

        chunk.metadata["crop_scope"] = scope

    return chunks


def scope_covers(scope: str, crop: str) -> bool:
    """Whether a chunk tagged with `scope` may be cited for `crop`."""
    if scope == NON_CROP_SCOPE:
        return False
    if scope == GENERAL_SCOPE:
        return True
    return crop in scope.split(SCOPE_SEPARATOR)


def load_documents() -> list[Document]:
    """One cleaned Document per label page, citation metadata attached at load
    time. EPA approval-letter pages are skipped.
    """
    product_names = {p.epa_reg_no: p.name for p in list_products()}
    documents: list[Document] = []

    for path in sorted(LABELS_DIR.glob("*.pdf")):
        company, product_code, _date = path.stem.split("-")
        reg_no = f"{int(company)}-{int(product_code)}"
        name = product_names[reg_no]  # unknown PDF -> loud KeyError, on purpose

        reader = PdfReader(path)
        skip_through = _front_matter_pages(reader)

        # Parts are running headers: carried forward until another one appears.
        current_part: str | None = None
        current_section: str | None = None

        for page_no, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""

            page_part, page_section = _headings(raw)
            if page_part:
                current_part = page_part
                current_section = None  # a new part restarts section numbering
            if page_section:
                current_section = page_section

            if page_no <= skip_through:
                continue

            text = clean_page_text(raw)
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
                        # Chroma metadata must be scalar, so absent is "".
                        "part": current_part or "",
                        "section": current_section or "",
                    },
                )
            )

    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """Split pages into overlapping chunks. Each inherits its page's metadata,
    then is scoped to the crops that govern it on the page it came from.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
        keep_separator="end",
    )
    chunks = splitter.split_documents(documents)

    for chunk in chunks:
        chunk.page_content = chunk.page_content.lstrip(" \t\r\n.?!")

    return scope_chunks(chunks)


def load_chunks() -> list[Document]:
    """Every label PDF, cleaned, structured, and chunked, ready for the store."""
    return split_documents(load_documents())
