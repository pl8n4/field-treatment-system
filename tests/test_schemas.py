from datetime import date

import pytest
from pydantic import ValidationError

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
