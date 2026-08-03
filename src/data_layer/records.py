from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from data_layer.schemas import Application, FarmField, ProductLimits

"""
Accessors for the records in data, every read of that 
directory goes through here
"""

DATA_DIR = Path(__file__).parents[2] / "data"

M = TypeVar("M", bound=BaseModel)

@lru_cache(maxsize=None)
def _load(filename: str, model: type[M]) -> tuple[M, ...]:
    """Read a JSON array into validated models. Cached; the files never change."""
    rows = json.loads((DATA_DIR / filename).read_text())
    return tuple(model.model_validate(row) for row in rows)


def _resolve(rows: tuple[M, ...], text: str, *keys: str) -> M | None:
    """Match what the user typed to exactly one record, or None.

    A partial match answers only when it is unambiguous. Both a miss and an
    ambiguous match become a question for the user.
    """
    needle = text.strip().casefold()
    matches = [
        row for row in rows
        if any(needle in getattr(row, key).casefold() for key in keys)
    ]
    return matches[0] if len(matches) == 1 else None


# --- Fields ---


def list_fields() -> tuple[FarmField, ...]:
    return _load("fields.json", FarmField)


def find_field(name_or_id: str) -> FarmField | None:
    return _resolve(list_fields(), name_or_id, "id", "name")


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
    return _resolve(list_products(), name, "name")
