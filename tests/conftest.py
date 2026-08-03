import sys
from datetime import date
from pathlib import Path

import pytest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from schemas import (  # noqa: E402
    ApplicationRecord,
    EvidenceChunk,
    FieldRecord,
    ProductRecord,
    TreatmentPlan,
    WeatherForecast,
)


@pytest.fixture
def field_record() -> FieldRecord:
    return FieldRecord(
        field_id="F001",
        crop="soybeans",
        acres=80,
        trait_package="Example Trait",
        growth_stage="R2",
        expected_harvest_date=date(2026, 10, 1),
        latitude=38.627,
        longitude=-90.1994,
        sensitive_site_distance_feet=300,
    )


@pytest.fixture
def product_record() -> ProductRecord:
    return ProductRecord(
        product_name="Example Product",
        supported_crops=["soybeans"],
        compatible_traits=["Example Trait"],
        allowed_growth_stages=["V6", "R1", "R2"],
        minimum_rate=10,
        maximum_rate=20,
        seasonal_maximum_rate=40,
        maximum_wind_mph=15,
        maximum_temperature_f=90,
        required_buffer_feet=110,
        rei_hours=24,
        phi_days=30,
    )


@pytest.fixture
def application_history() -> list[ApplicationRecord]:
    return [
        ApplicationRecord(
            field_id="F001",
            product_name="Example Product",
            application_date=date(2026, 7, 3),
            rate=10,
        )
    ]


@pytest.fixture
def weather() -> WeatherForecast:
    return WeatherForecast(
        forecast_date=date(2026, 8, 2),
        high_temperature_f=82,
        wind_speed_mph=8,
        wind_direction="NW",
        precipitation_probability=20,
        source="Test weather",
        cached=True,
    )


@pytest.fixture
def treatment_plan() -> TreatmentPlan:
    return TreatmentPlan(
        field_id="F001",
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
def evidence() -> list[EvidenceChunk]:
    return [
        EvidenceChunk(
            content="Test product-label evidence.",
            source="test-label.pdf",
            page=1,
            product_name="Example Product",
            registration_number="00000-000",
        )
    ]
