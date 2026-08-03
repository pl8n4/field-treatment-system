from graph import AgriculturalWorkflow
from schemas import (
    ApplicationRecord,
    FieldRecord,
    ProductRecord,
    TreatmentPlan,
    WeatherForecast,
)


def checks_by_name(update: dict) -> dict:
    return {check.rule_name: check for check in update["rule_result"].checks}


def build_state(
    treatment_plan: TreatmentPlan,
    field_record: FieldRecord,
    product_record: ProductRecord,
    application_history: list[ApplicationRecord],
    weather: WeatherForecast,
) -> dict:
    return {
        "plan": treatment_plan,
        "field_record": field_record,
        "product_record": product_record,
        "application_history": application_history,
        "weather": weather,
    }


def test_rule_engine_passes_compliant_plan(
    treatment_plan: TreatmentPlan,
    field_record: FieldRecord,
    product_record: ProductRecord,
    application_history: list[ApplicationRecord],
    weather: WeatherForecast,
) -> None:
    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_plan,
            field_record,
            product_record,
            application_history,
            weather,
        )
    )

    result = update["rule_result"]
    assert result.all_passed is True
    assert len(result.checks) == 9
    assert all(check.passed for check in result.checks)
    assert update["audit_log"] == ["Rule engine completed: 9/9 checks passed."]


def test_rule_engine_detects_fixable_rate_failures(
    treatment_plan: TreatmentPlan,
    field_record: FieldRecord,
    product_record: ProductRecord,
    application_history: list[ApplicationRecord],
    weather: WeatherForecast,
) -> None:
    excessive_rate_plan = treatment_plan.model_copy(update={"proposed_rate": 35})

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
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
    treatment_plan: TreatmentPlan,
    field_record: FieldRecord,
    product_record: ProductRecord,
    application_history: list[ApplicationRecord],
    weather: WeatherForecast,
) -> None:
    application_history.append(
        ApplicationRecord(
            field_id="F001",
            product_name="Different Product",
            application_date=treatment_plan.treatment_date,
            rate=100,
        )
    )
    plan = treatment_plan.model_copy(update={"proposed_rate": 20})

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            plan,
            field_record,
            product_record,
            application_history,
            weather,
        )
    )

    assert checks_by_name(update)["seasonal_maximum_rate"].passed is True


def test_rule_engine_detects_hard_crop_violation(
    treatment_plan: TreatmentPlan,
    field_record: FieldRecord,
    product_record: ProductRecord,
    application_history: list[ApplicationRecord],
    weather: WeatherForecast,
) -> None:
    incompatible_field = field_record.model_copy(update={"crop": "corn"})

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
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
    treatment_plan: TreatmentPlan,
    field_record: FieldRecord,
    product_record: ProductRecord,
    application_history: list[ApplicationRecord],
    weather: WeatherForecast,
) -> None:
    early_harvest_field = field_record.model_copy(
        update={"expected_harvest_date": treatment_plan.treatment_date}
    )

    update = AgriculturalWorkflow._rule_engine_node(
        build_state(
            treatment_plan,
            early_harvest_field,
            product_record,
            application_history,
            weather,
        )
    )

    assert checks_by_name(update)["phi_before_harvest"].passed is False
