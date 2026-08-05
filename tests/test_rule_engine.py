from datetime import date

from data_layer.schemas import Application, FarmField, ProductLimits, WeatherForecast
from workflow.graph import AgriculturalWorkflow
from workflow.schemas import TreatmentPlan, TreatmentRequest


def checks_by_name(update: dict) -> dict:
    return {check.rule_name: check for check in update["rule_result"].checks}


def build_state(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> dict:
    return {
        "request": treatment_request,
        "plan": treatment_plan,
        "field_record": field_record,
        "product_record": product_record,
        "application_history": application_history,
        "weather": weather,
    }


def test_rule_engine_passes_compliant_plan(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            treatment_plan,
            field_record,
            product_record,
            application_history,
            weather,
        )
    )

    result = update["rule_result"]
    assert result.all_passed is True
    assert len(result.checks) == 16
    assert all(check.passed for check in result.checks)
    assert update["audit_log"] == ["Rule engine completed: 16/16 checks passed."]


def test_rule_engine_detects_fixable_rate_failures(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    excessive_rate_plan = treatment_plan.model_copy(update={"proposed_rate": 35})

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            excessive_rate_plan,
            field_record,
            product_record,
            application_history,
            weather,
        )
    )
    checks = checks_by_name(update)

    assert checks["maximum_rate"].passed is False
    assert checks["maximum_rate"].severity == "fixable"
    assert checks["seasonal_maximum_rate"].passed is False
    assert update["rule_result"].all_passed is False


def test_rule_engine_counts_only_matching_product_history(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    application_history.append(
        Application(
            id="A-002",
            field_id="F-01",
            product="Different Product",
            applied_on=treatment_plan.treatment_date,
            rate_fl_oz_per_acre=100,
        )
    )
    plan = treatment_plan.model_copy(update={"proposed_rate": 20})

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            plan,
            field_record,
            product_record,
            application_history,
            weather,
        )
    )

    assert checks_by_name(update)["seasonal_maximum_rate"].passed is True


def test_rule_engine_detects_hard_crop_violation(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    incompatible_field = field_record.model_copy(update={"crop": "corn"})

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            treatment_plan,
            incompatible_field,
            product_record,
            application_history,
            weather,
        )
    )
    crop_check = checks_by_name(update)["crop_compatibility"]

    assert crop_check.passed is False
    assert crop_check.severity == "hard_violation"


def test_rule_engine_detects_phi_violation(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    early_harvest_field = field_record.model_copy(
        update={"expected_harvest_date": treatment_plan.treatment_date}
    )

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            treatment_plan,
            early_harvest_field,
            product_record,
            application_history,
            weather,
        )
    )

    assert checks_by_name(update)["phi_before_harvest"].passed is False


def test_rule_engine_detects_plan_identity_mismatches(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    mismatched_plan = treatment_plan.model_copy(
        update={
            "field_id": "F-99",
            "product_name": "Different Product",
            "treatment_date": date(2026, 8, 3),
        }
    )

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            mismatched_plan,
            field_record,
            product_record,
            application_history,
            weather,
        )
    )
    checks = checks_by_name(update)

    assert checks["field_identity"].passed is False
    assert checks["product_identity"].passed is False
    assert checks["requested_treatment_date"].passed is False
    assert checks["field_identity"].severity == "fixable"
    assert checks["product_identity"].severity == "fixable"
    assert checks["requested_treatment_date"].severity == "fixable"


def test_rule_engine_detects_requested_value_mismatches(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    mismatched_plan = treatment_plan.model_copy(
        update={
            "proposed_rate": 12,
            "treated_acres": 75,
        }
    )

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            mismatched_plan,
            field_record,
            product_record,
            application_history,
            weather,
        )
    )
    checks = checks_by_name(update)

    assert checks["requested_rate"].passed is False
    assert checks["requested_acres"].passed is False
    assert checks["requested_rate"].severity == "fixable"
    assert checks["requested_acres"].severity == "fixable"


def test_growth_stage_window_accepts_stages_past_v8(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    """V10 is pre-bloom, and "up to but not including R1" permits it."""
    product = product_record.model_copy(
        update={
            "earliest_growth_stage": "VE",
            "latest_growth_stage": None,
            "latest_growth_stage_exclusive": "R1",
        }
    )

    for stage, expected in (("V8", True), ("V10", True), ("R1", False)):
        update = AgriculturalWorkflow._rule_engine_node(
            build_state(
                treatment_request,
                treatment_plan,
                field_record.model_copy(update={"growth_stage": stage}),
                product,
                application_history,
                weather,
            )
        )
        check = checks_by_name(update)["growth_stage_window"]
        assert check.passed is expected, f"{stage}: {check.explanation}"


def test_unrecognised_growth_stage_is_not_reported_as_a_breach(
    treatment_request: TreatmentRequest,
    treatment_plan: TreatmentPlan,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
) -> None:
    """It still fails, but must not claim the label was broken."""
    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_request,
            treatment_plan,
            field_record.model_copy(update={"growth_stage": "V4.5"}),
            product_record,
            application_history,
            weather,
        )
    )

    check = checks_by_name(update)["growth_stage_window"]
    assert check.passed is False
    assert "not recognised" in check.explanation
