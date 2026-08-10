"""The intake form's rules, tested without driving the interface."""

from __future__ import annotations

from ui import request


def build(**overrides: object) -> str:
    defaults: dict[str, object] = {
        "crop": "Soybean",
        "product": "Enlist One",
        "state": "Missouri",
        "field_id": "F-02",
        "acreage": None,
        "application_rate": None,
        "treatment_date": "2026-08-06",
        "question": "Broadleaf weeds are through the canopy.",
    }
    defaults.update(overrides)
    return request.build_request(**defaults)  # type: ignore[arg-type]


def test_request_always_states_the_required_facts() -> None:
    message = build()

    assert "Broadleaf weeds are through the canopy." in message
    assert "The field ID is F-02." in message
    assert "The crop is Soybean." in message
    assert "The proposed product is Enlist One." in message
    assert "The proposed treatment date is 2026-08-06." in message
    assert "The field is located in Missouri." in message


def test_empty_acreage_and_rate_are_omitted_entirely() -> None:
    """Omission is meaningful: it lets the workflow fall back to its defaults."""
    message = build(acreage=None, application_rate=None)

    assert "acres" not in message
    assert "application rate" not in message


def test_zero_acreage_and_rate_are_treated_as_unset() -> None:
    message = build(acreage=0, application_rate=0)

    assert "acres" not in message
    assert "application rate" not in message


def test_supplied_acreage_and_rate_are_stated_without_trailing_zeros() -> None:
    message = build(acreage=40.0, application_rate=32.5)

    assert "Treat 40 acres." in message
    assert "The requested application rate is 32.5 fl oz per acre." in message


def test_blank_location_is_omitted() -> None:
    assert "located in" not in build(state="   ")


def test_missing_fields_are_keyed_by_field() -> None:
    errors = request.missing_fields(
        crop="Soybean",
        product="   ",
        field_id="F-02",
        question="",
    )

    assert errors == {
        "product": "Enter the product.",
        "question": "Enter the treatment request.",
    }


def test_no_missing_fields_when_all_are_present() -> None:
    assert (
        request.missing_fields(
            crop="Soybean",
            product="Enlist One",
            field_id="F-02",
            question="Weeds.",
        )
        == {}
    )
