import sys
from datetime import date
from pathlib import Path

import pytest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from data_layer.schemas import (  # noqa: E402
    Application,
    FarmField,
    LabelChunk,
    ProductLimits,
    TraitPackage,
    WeatherForecast,
)
from workflow.schemas import TreatmentPlan, TreatmentRequest  # noqa: E402


@pytest.fixture
def treatment_request() -> TreatmentRequest:
    return TreatmentRequest(
        field_id="F-01",
        crop="soybean",
        observed_issue="fungal disease",
        proposed_product="Example Product",
        proposed_date="2026-08-02",
        acres=80,
        requested_rate=10,
    )


@pytest.fixture
def field_record() -> FarmField:
    return FarmField(
        id="F-01",
        name="Test Field",
        acres=80.0,
        crop="soybean",
        trait_package=TraitPackage.XTENDFLEX,
        growth_stage="R2",
        expected_harvest_date=date(2026, 10, 1),
        latitude=38.627,
        longitude=-90.1994,
        feet_to_sensitive_site=300,
    )


@pytest.fixture
def product_record() -> ProductLimits:
    return ProductLimits(
        name="Example Product",
        epa_reg_no="00000-000",
        supported_crops=["soybean"],
        allowed_traits=[TraitPackage.XTENDFLEX],
        earliest_growth_stage="V6",
        latest_growth_stage="R2",
        max_rate_fl_oz_per_acre=20,
        max_seasonal_fl_oz_per_acre=40,
        max_applications_per_season=2,
        wind_min_mph=3,
        wind_max_mph=15,
        downwind_buffer_ft=110,
        rei_hours=24,
        phi_days=30,
    )


@pytest.fixture
def application_history() -> list[Application]:
    return [
        Application(
            id="A-001",
            field_id="F-01",
            product="Example Product",
            applied_on=date(2026, 7, 3),
            rate_fl_oz_per_acre=10,
        )
    ]


@pytest.fixture
def weather() -> WeatherForecast:
    return WeatherForecast(
        latitude=38.627,
        longitude=-90.1994,
        target_date=date(2026, 8, 2),
        high_temp_f=82,
        wind_speed_mph=8,
        wind_direction_deg=315,
        precipitation_probability_pct=20,
    )


@pytest.fixture
def treatment_plan() -> TreatmentPlan:
    return TreatmentPlan(
        field_id="F-01",
        product_name="Example Product",
        treatment_date=date(2026, 8, 2),
        proposed_rate=10,
        treated_acres=80,
        timing_summary="Test timing summary.",
        buffer_summary="Test buffer summary.",
        rei_summary="Restricted-entry interval is 24 hours.",
        phi_summary="Pre-harvest interval is 30 days.",
        citations=["test-label.pdf, page 1"],
        assumptions=[],
        human_review_required=True,
    )


@pytest.fixture
def evidence() -> list[LabelChunk]:
    return [
        LabelChunk(
            text="Test product-label evidence.",
            source="test-label.pdf",
            page=1,
            product="Example Product",
            epa_reg_no="00000-000",
        )
    ]
