from datetime import date

import pytest

import data_layer.records as records
from data_layer.schemas import Application, FarmField, ProductLimits, TraitPackage


def make_field(field_id: str, name: str) -> FarmField:
    return FarmField(
        id=field_id,
        name=name,
        acres=80,
        crop="soybean",
        trait_package=TraitPackage.XTENDFLEX,
        growth_stage="R2",
        expected_harvest_date=date(2026, 10, 1),
        latitude=38.627,
        longitude=-90.1994,
        feet_to_sensitive_site=300,
    )


def test_find_field_resolves_case_insensitive_id_and_unique_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fields = (
        make_field("F-01", "North Forty"),
        make_field("F-02", "South Creek"),
    )
    monkeypatch.setattr(records, "list_fields", lambda: fields)

    assert records.find_field("f-01") == fields[0]
    assert records.find_field(" creek ") == fields[1]


@pytest.mark.parametrize("query", ["", "   ", "unknown"])
def test_find_field_returns_none_for_empty_or_unknown_input(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    monkeypatch.setattr(
        records,
        "list_fields",
        lambda: (make_field("F-01", "North Forty"),),
    )

    assert records.find_field(query) is None


def test_find_field_rejects_ambiguous_partial_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fields = (
        make_field("F-01", "North Forty"),
        make_field("F-02", "North Creek"),
    )
    monkeypatch.setattr(records, "list_fields", lambda: fields)

    assert records.find_field("north") is None


def test_find_product_is_case_insensitive_and_rejects_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = (
        ProductLimits(name="Example One", epa_reg_no="1-1"),
        ProductLimits(name="Example Two", epa_reg_no="1-2"),
    )
    monkeypatch.setattr(records, "list_products", lambda: products)

    assert records.find_product("example one") == products[0]
    assert records.find_product("example") is None


def test_applications_for_filters_field_product_and_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applications = (
        Application(
            id="A-1",
            field_id="F-01",
            product="Product A",
            applied_on=date(2026, 5, 1),
            rate_fl_oz_per_acre=10,
        ),
        Application(
            id="A-2",
            field_id="F-01",
            product="Product B",
            applied_on=date(2026, 6, 1),
            rate_fl_oz_per_acre=20,
        ),
        Application(
            id="A-3",
            field_id="F-01",
            product="Product A",
            applied_on=date(2025, 5, 1),
            rate_fl_oz_per_acre=30,
        ),
        Application(
            id="A-4",
            field_id="F-02",
            product="Product A",
            applied_on=date(2026, 5, 1),
            rate_fl_oz_per_acre=40,
        ),
    )
    monkeypatch.setattr(records, "list_applications", lambda: applications)

    matches = records.applications_for(
        "F-01",
        product="Product A",
        season_year=2026,
    )

    assert [application.id for application in matches] == ["A-1"]
    assert records.seasonal_total_applied("F-01", "Product A", 2026) == 10
