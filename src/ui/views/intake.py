"""The intake form: the structured request the workflow starts from.

Deliberately not an ``st.form``. Form widgets suppress reruns, so the text
input revealed by choosing "Other" did not appear until the form had already
been submitted — the first submit always failed with the field still blank.
Outside a form the follow-up input appears as soon as "Other" is chosen, and
the selected field's record can be shown while the request is being written.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from data_layer.records import list_fields, list_products
from data_layer.schemas import FarmField
from data_layer.weather import FORECAST_HORIZON_DAYS
from ui import progress
from ui import request as request_builder
from ui import state as session
from ui.components import facts

OTHER = "Other"
CROPS = ["Soybean", "Corn", "Wheat", OTHER]
LOCATIONS = ["Missouri", OTHER]


def render() -> None:
    workflow = st.session_state.workflow

    fields = list_fields()
    products = list_products()
    field_labels = [f"{field.id} — {field.name}" for field in fields] + [OTHER]
    product_names = [product.name for product in products] + [OTHER]

    subject_column, detail_column = st.columns(2, gap="large")

    with subject_column:
        st.markdown("**What is being treated**")

        crop_choice = st.selectbox("Crop", CROPS)
        crop = st.text_input("Other crop") if crop_choice == OTHER else crop_choice
        crop_error = st.empty()

        field_choice = st.selectbox("Field ID", field_labels)
        field_id = (
            st.text_input("Other field ID")
            if field_choice == OTHER
            else field_choice.split(" — ", maxsplit=1)[0]
        )
        field_error = st.empty()

        location_choice = st.selectbox("State / Location", LOCATIONS)
        location = (
            st.text_input("Other state/location")
            if location_choice == OTHER
            else location_choice
        )

    # Both selections are made in the column above, so the defaults they imply
    # are known by the time the numeric inputs below are drawn.
    field_record = next((field for field in fields if field.id == field_id), None)

    with detail_column:
        st.markdown("**What is being applied**")

        product_choice = st.selectbox("Product", product_names)
        product = (
            st.text_input("Other product")
            if product_choice == OTHER
            else product_choice
        )
        product_error = st.empty()

        product_record = next((item for item in products if item.name == product), None)
        default_rate = (
            product_record.default_rate_fl_oz_per_acre if product_record else None
        )

        application_rate = st.number_input(
            "Application rate (fl oz/acre)",
            min_value=0.0,
            value=None,
            step=1.0,
            placeholder=_default_hint(default_rate, "the product label's default"),
            help=(
                "Leave empty to use the product label's default rate. The "
                "greyed value is what will be used."
            ),
        )
        acreage = st.number_input(
            "Area to treat (acres)",
            min_value=0.0,
            value=None,
            step=1.0,
            placeholder=_default_hint(
                field_record.acres if field_record else None,
                "the field's full recorded acreage",
            ),
            help=(
                "Leave empty to treat the field's full recorded acreage. The "
                "greyed value is what will be used."
            ),
        )
        treatment_date = st.date_input(
            "Treatment date",
            min_value=date.today(),
            max_value=date.today() + timedelta(days=FORECAST_HORIZON_DAYS),
            help=(
                "The forecast the compliance checks rely on reaches about "
                f"{FORECAST_HORIZON_DAYS} days ahead."
            ),
        )

    _render_field_record(field_record)

    question = st.text_area(
        "Treatment Request",
        placeholder="Describe the observed issue and the treatment you want.",
        height=120,
    )
    question_error = st.empty()

    submitted = st.button(
        "Submit request",
        type="primary",
        icon=":material/send:",
    )
    if not submitted:
        return

    errors = request_builder.missing_fields(
        crop=crop,
        product=product,
        field_id=field_id,
        question=question,
    )
    if errors:
        placeholders = {
            "crop": crop_error,
            "product": product_error,
            "field_id": field_error,
            "question": question_error,
        }
        for key, message in errors.items():
            placeholders[key].error(message, icon=":material/error:")
        return

    workflow_request = request_builder.build_request(
        crop=crop,
        product=product,
        state=location,
        field_id=field_id,
        acreage=acreage,
        application_rate=application_rate,
        treatment_date=treatment_date.isoformat(),
        question=question,
    )
    with progress.WorkflowProgress() as running:
        next_state = workflow.start(
            question=workflow_request,
            thread_id=st.session_state.thread_id,
            on_node=running.record,
        )
    session.save_workflow_state(next_state)
    st.rerun()


def _default_hint(value: float | None, fallback: str) -> str:
    """Placeholder text for an optional number: the real default when known.

    Shown rather than pre-filled on purpose. An empty input means "unspecified"
    and lets the workflow fall back to its own records; typing the same number
    in means "the reviewer asked for exactly this", which the intake decision
    and the rule engine treat as a different thing.
    """
    if value is None:
        return f"Defaults to {fallback}"
    return f"{value:g} (default)"


def _render_field_record(record: FarmField | None) -> None:
    """Show the record behind the chosen field, before the request is written.

    The trait package and growth stage decide whether a product can legally go
    on this field at all, so they are worth seeing while choosing a product.
    """
    if record is None:
        return

    st.caption(f"FIELD RECORD · {record.name}")
    facts.grid(
        [
            ("Recorded area", f"{record.acres:g} acres"),
            ("Growth stage", record.growth_stage),
            ("Trait package", record.trait_package.value.replace("_", " ")),
            ("Expected harvest", record.expected_harvest_date.isoformat()),
        ],
        per_row=4,
    )
