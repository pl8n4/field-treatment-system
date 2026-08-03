"""Accessors for the records in data, every read of that
directory goes through here
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from data_layer.schemas import Application, FarmField, ProductLimits

DATA_DIR = Path(__file__).parents[2] / "data"

M = TypeVar("M", bound=BaseModel)


@cache
def _load(filename: str, model: type[M]) -> tuple[M, ...]:
    """Read a JSON array into validated models. Cached; the files never change."""
    rows = json.loads((DATA_DIR / filename).read_text())
    return tuple(model.model_validate(row) for row in rows)


def _resolve(
    rows: tuple[M, ...],
    text: str,
    *,
    exact_keys: tuple[str, ...] = (),
    partial_keys: tuple[str, ...] = (),
) -> M | None:
    """Resolve text to one record using exact keys before partial-match keys.

    Exact keys match case-insensitively by equality. If no exact key matches,
    partial keys match case-insensitively by substring, but only when that
    result is unambiguous. Empty, missing, and ambiguous input returns None.
    """
    needle = text.strip().casefold()
    if not needle:
        return None

    matches = [
        row
        for row in rows
        if any(needle == getattr(row, key).casefold() for key in exact_keys)
    ]
    if matches:
        return matches[0] if len(matches) == 1 else None

    matches = [
        row
        for row in rows
        if any(needle in getattr(row, key).casefold() for key in partial_keys)
    ]
    return matches[0] if len(matches) == 1 else None


# --- Fields ---


def list_fields() -> tuple[FarmField, ...]:
    return _load("fields.json", FarmField)


def find_field(name_or_id: str) -> FarmField | None:
    return _resolve(
        list_fields(), name_or_id, exact_keys=("id",), partial_keys=("name",)
    )


# --- Application history ---


def list_applications() -> tuple[Application, ...]:
    return _load("applications.json", Application)


def applications_for(
    field_id: str,
    *,
    product: str | None = None,
    season_year: int | None = None,
) -> list[Application]:
    """Spray history for a field, optionally narrowed to one product or season"""
    return [
        app
        for app in list_applications()
        if app.field_id == field_id
        and (product is None or app.product == product)
        and (season_year is None or app.applied_on.year == season_year)
    ]


def seasonal_total_applied(field_id: str, product: str, season_year: int) -> float:
    """Total fl oz/acre of one product already applied to a field this season"""
    history = applications_for(field_id, product=product, season_year=season_year)
    return sum(app.rate_fl_oz_per_acre for app in history)


# --- Product limits ---


def list_products() -> tuple[ProductLimits, ...]:
    return _load("products.json", ProductLimits)


def find_product(name: str) -> ProductLimits | None:
    return _resolve(list_products(), name, partial_keys=("name",))
