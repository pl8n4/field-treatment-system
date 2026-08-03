"""Pydantic models for the data layer: farm records, label facts, weather, chunks."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel

# Soybean growth stages in label order
SOYBEAN_STAGES = (
    "VE",
    "VC",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "V8",
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "R6",
    "R7",
    "R8",
)


class TraitPackage(str, Enum):
    """Herbicide-tolerance trait stack a field is planted to.

    The stack decides which herbicides can go over the top without killing the
    crop, which is what makes the trait check a safety rule rather than a
    preference. Each comment lists the tolerances that stack confers, and
    together they explain every allowed_traits list in products.json.
    """

    CONVENTIONAL = "conventional"  # no tolerance traits
    ROUNDUP_READY_2_XTEND = "roundup_ready_2_xtend"  # glyphosate, dicamba
    XTENDFLEX = "xtendflex"  # glyphosate, dicamba, glufosinate
    ENLIST_E3 = "enlist_e3"  # glyphosate, 2,4-D choline, glufosinate
    LIBERTYLINK = "libertylink"  # glufosinate


# --- Farm records ---


class FarmField(BaseModel):
    """One field in the farm's records."""

    id: str
    name: str
    # Tillable acres in the whole field, a request may treat fewer
    acres: float
    crop: str = "soybean"
    trait_package: TraitPackage
    growth_stage: str
    expected_harvest_date: date
    latitude: float
    longitude: float
    feet_to_sensitive_site: int


class Application(BaseModel):
    """A past spray event, used for cumulative seasonal rate checks."""

    id: str
    field_id: str
    product: str
    applied_on: date
    rate_fl_oz_per_acre: float


# --- Label knowledge ---


class ProductLimits(BaseModel):
    """One product's label rules in structured form.

    A None limit means the label sets no such restriction.
    """

    name: str
    epa_reg_no: str

    # Crops the label registers the product for, read from its crop-use sections
    # labels also cover orchard, vegetable, and non-crop sites that are not listed here
    supported_crops: list[str] | None = None

    # None where the product has no trait restriction at all: a fungicide has no
    # herbicidal activity, and a harvest-aid desiccant is applied to kill the crop.
    # An empty list would mean no trait may be sprayed, which is never true.
    allowed_traits: list[TraitPackage] | None = None
    earliest_growth_stage: str | None = None
    latest_growth_stage: str | None = None
    # Where to start when the request names no rate
    default_rate_fl_oz_per_acre: float | None = None
    max_rate_fl_oz_per_acre: float | None = None
    max_seasonal_fl_oz_per_acre: float | None = None
    max_applications_per_season: int | None = None
    rei_hours: int | None = None  # restricted-entry interval
    phi_days: int | None = None  # pre-harvest interval
    wind_min_mph: float | None = None
    wind_max_mph: float | None = None
    downwind_buffer_ft: int | None = None
    # No max_temp_f: none of the five labels sets a numeric air-temperature
    # ceiling. They prohibit spraying into a temperature inversion instead,
    # which is a condition rather than a threshold and is not modelled here.


class LabelChunk(BaseModel):
    """A slice of one page of an official PPLS label PDF."""

    text: str
    product: str
    epa_reg_no: str
    page: int
    source: str  # PDF filename, for the citation list


# --- Weather ---


class WeatherForecast(BaseModel):
    """Forecast for one field on one day. Part of the compliance record."""

    latitude: float
    longitude: float
    target_date: date
    high_temp_f: float
    wind_speed_mph: float
    wind_direction_deg: int
    precipitation_probability_pct: int
