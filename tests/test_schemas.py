from datetime import date

import pytest
from pydantic import ValidationError

from data_layer.schemas import FarmField, ProductLimits
from workflow.schemas import TreatmentPlan, TreatmentRequest


@pytest.mark.parametrize("field_name", ["acres", "requested_rate"])
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_treatment_request_rejects_nonpositive_values(
    field_name: str,
    invalid_value: float,
) -> None:
    with pytest.raises(ValidationError):
        TreatmentRequest.model_validate({field_name: invalid_value})


@pytest.mark.parametrize("field_name", ["proposed_rate", "treated_acres"])
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_treatment_plan_rejects_nonpositive_values(
    field_name: str,
    invalid_value: float,
) -> None:
    plan_data = {
        "field_id": "F-01",
        "product_name": "Example Product",
        "treatment_date": date(2026, 8, 2),
        "proposed_rate": 10,
        "treated_acres": 80,
        "timing_summary": "Test timing summary.",
        "buffer_summary": "Test buffer summary.",
        "rei_summary": "Test REI summary.",
        "phi_summary": "Test PHI summary.",
        "citations": ["test-label.pdf, page 1"],
    }
    plan_data[field_name] = invalid_value

    with pytest.raises(ValidationError):
        TreatmentPlan.model_validate(plan_data)


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_farm_field_rejects_nonpositive_acres(
    invalid_value: float,
) -> None:
    field_data = {
        "id": "F-01",
        "name": "Test Field",
        "acres": invalid_value,
        "crop": "soybean",
        "trait_package": "xtendflex",
        "growth_stage": "V4",
        "expected_harvest_date": date(2026, 10, 20),
        "latitude": 39.2451,
        "longitude": -92.3086,
        "feet_to_sensitive_site": 1450,
    }

    with pytest.raises(ValidationError):
        FarmField.model_validate(field_data)


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_product_limits_rejects_nonpositive_default_rate(
    invalid_value: float,
) -> None:
    product_data = {
        "name": "Test Product",
        "epa_reg_no": "00000-000",
        "default_rate_fl_oz_per_acre": invalid_value,
    }

    with pytest.raises(ValidationError):
        ProductLimits.model_validate(product_data)
