"""Crop scoping of label chunks — which label text a treatment may cite.
The Roundup master label is why: 171 pages, 52 of turf, 8 of soybean.
"""

import pytest
from langchain_core.documents import Document

from data_layer.corpus import (
    GENERAL_SCOPE,
    LABELS_DIR,
    NON_CROP_SCOPE,
    _front_matter_pages,
    crop_scope,
    load_chunks,
    scope_chunks,
    scope_covers,
)

pytestmark = pytest.mark.skipif(
    not any(LABELS_DIR.glob("*.pdf")), reason="label PDFs are not present"
)


def test_text_naming_no_crop_is_general():
    """A wind rule names no crop and must survive every crop filter."""
    assert crop_scope("Do not apply when wind speed exceeds 10 mph.") == GENERAL_SCOPE
    assert crop_scope("Apply to cotton and soybean.") == "cotton+soybean"


def test_non_crop_part_overrides_the_text():
    """Nothing under the turf part applies to a crop, whatever it says."""
    assert (
        crop_scope(
            "Apply to ornamental turf adjacent to corn.",
            part="II. DIRECTIONS FOR USE ON INDUSTRIAL, TURF AND ORNAMENTAL SITES",
        )
        == NON_CROP_SCOPE
    )


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (GENERAL_SCOPE, True),
        ("soybean", True),
        ("corn+cotton+soybean", True),
        ("corn", False),
        (NON_CROP_SCOPE, False),
        ("soybeanoid", False),  # substring must not admit
    ],
)
def test_scope_covers_soybean(scope, expected):
    assert scope_covers(scope, "soybean") is expected


def _page(source: str, page: int, *texts: str) -> list[Document]:
    return [
        Document(
            page_content=text, metadata={"source": source, "page": page, "part": ""}
        )
        for text in texts
    ]


def test_a_crop_heading_governs_the_chunks_beneath_it():
    """Rates and intervals are printed under a crop heading and never repeat it."""
    scoped = scope_chunks(
        _page(
            "a.pdf",
            7,
            "WHEAT Apply 4.0 fl oz per acre.",
            "Pre-Harvest Interval (PHI): 35 days. Do not graze within 30 days.",
        )
    )
    assert [c.metadata["crop_scope"] for c in scoped] == ["wheat", "wheat"]


def test_product_wide_directions_are_not_captured_by_the_heading_above_them():
    """A boom height holds for every crop, whatever it was printed under."""
    scoped = scope_chunks(
        _page(
            "a.pdf",
            7,
            "Do not allow spray to drift onto adjacent cotton.",
            "Groundboom Application: do not exceed 24 inches above the canopy.",
            "Storage and Disposal: store in the original container.",
        )
    )
    assert [c.metadata["crop_scope"] for c in scoped[1:]] == [
        GENERAL_SCOPE,
        GENERAL_SCOPE,
    ]


def test_the_governing_crop_does_not_cross_a_page_break():
    """A crop section ends at the page it ends on; the next page starts clean."""
    scoped = scope_chunks(
        _page("a.pdf", 7, "COTTON Apply 22.0 fl oz per acre.")
        + _page("a.pdf", 8, "Do not apply more than twice per season.")
    )
    assert [c.metadata["crop_scope"] for c in scoped] == ["cotton", GENERAL_SCOPE]


@pytest.fixture(scope="module")
def chunks():
    return load_chunks()


def test_epa_cover_letters_are_never_indexed(chunks):
    """The approval letter is correspondence about the label, not the label."""
    from pypdf import PdfReader

    for path in sorted(LABELS_DIR.glob("*.pdf")):
        assert _front_matter_pages(PdfReader(path)) > 0, path.name
    assert min(c.metadata["page"] for c in chunks) > 2


def test_roundup_turf_pages_are_excluded_from_soybean(chunks):
    turf = [
        c
        for c in chunks
        if c.metadata["epa_reg_no"] == "524-659" and 116 <= c.metadata["page"] <= 167
    ]
    assert turf, "expected to find Part II chunks"
    assert not [c for c in turf if scope_covers(c.metadata["crop_scope"], "soybean")]


def test_another_crops_restriction_is_not_citable_for_soybean(chunks):
    """Delaro's wheat pre-harvest interval names no crop in its own 900
    characters — the heading is a few lines above it.
    """
    wheat_phi = [c for c in chunks if "Pyrenophora tritici-repentis" in c.page_content]
    assert wheat_phi, "expected the wheat disease table"
    assert not [
        c for c in wheat_phi if scope_covers(c.metadata["crop_scope"], "soybean")
    ]


def test_product_wide_restrictions_stay_citable_for_soybean(chunks):
    """Enlist prints its boom height under the drift-susceptible crop list."""
    boom = [c for c in chunks if "boom height" in c.page_content.lower()]
    assert boom, "expected boom height directions"
    assert all(scope_covers(c.metadata["crop_scope"], "soybean") for c in boom)


def test_roundup_soybean_directions_survive_the_filter(chunks):
    """The filter must cut noise without cutting the answer."""
    kept = [
        c
        for c in chunks
        if c.metadata["epa_reg_no"] == "524-659"
        and 84 <= c.metadata["page"] <= 91
        and scope_covers(c.metadata["crop_scope"], "soybean")
    ]
    assert len(kept) >= 10
