import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from data_layer.records import list_fields, list_products
from data_layer.weather import FORECAST_HORIZON_DAYS
from data_layer.work_orders import get_all_work_orders, init_db
from workflow.graph import AgriculturalWorkflow

st.set_page_config(page_title="AgriFlow AI", layout="wide")


def _as_dict(value: Any) -> dict[str, Any]:
    """Return workflow models and dictionaries in a display-friendly form."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def _build_request(
    *,
    crop: str,
    product: str,
    state: str,
    field_id: str,
    acreage: float,
    application_rate: str,
    treatment_date: str,
    question: str,
) -> str:
    """Translate the structured UI fields into the workflow's intake message."""
    parts = [
        question.strip(),
        f"The field ID is {field_id.strip()}.",
        f"The crop is {crop.strip()}.",
        f"The proposed product is {product.strip()}.",
        f"The proposed treatment date is {treatment_date}.",
    ]
    if state.strip():
        parts.append(f"The field is located in {state.strip()}.")
    if acreage > 0:
        parts.append(f"Treat {acreage:g} acres.")
    if application_rate.strip():
        parts.append(
            f"The requested application rate is {application_rate.strip()} fl oz per acre."
        )
    return " ".join(parts)


def _save_workflow_state(state: dict[str, Any]) -> None:
    st.session_state.awaiting_review = bool(state.get("__interrupt__"))
    st.session_state.last_state = state


init_db()

if "workflow" not in st.session_state:
    st.session_state.workflow = AgriculturalWorkflow()
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "awaiting_review" not in st.session_state:
    st.session_state.awaiting_review = False
if "last_state" not in st.session_state:
    st.session_state.last_state = None

workflow: AgriculturalWorkflow = st.session_state.workflow

st.title("AgriFlow AI")
st.write("Submit a field treatment request and review the recommendation.")

if st.session_state.awaiting_review and st.session_state.last_state:
    state = st.session_state.last_state
    plan = _as_dict(state.get("plan"))
    review = _as_dict(state.get("review"))
    sources = state.get("context_sources", [])

    st.subheader("Request Summary")
    st.info(
        "The workflow drafted a treatment plan and completed its compliance "
        "checks. Human acceptance is required before a simulated work order is "
        "created. No real treatment has been scheduled."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Recommendation")
        if plan:
            st.write(f"**Field ID:** {plan.get('field_id')}")
            st.write(f"**Product:** {plan.get('product_name')}")
            st.write(f"**Treatment Date:** {plan.get('treatment_date')}")
            st.write(f"**Application Rate:** {plan.get('proposed_rate')} fl oz/acre")
            st.write(f"**Acreage:** {plan.get('treated_acres')} acres")
            st.write(plan.get("timing_summary", ""))

        st.subheader("Weather and Safety Summary")
        if plan:
            st.write(plan.get("buffer_summary", ""))
            st.write(plan.get("rei_summary", ""))
            st.write(plan.get("phi_summary", ""))

    with col2:
        st.subheader("Compliance Review")
        if review:
            st.write(f"**Verdict:** {review.get('verdict', 'unknown')}")
            st.write(review.get("explanation", ""))
            for issue in review.get("issues", []):
                st.write(f"- {issue}")

        st.subheader("Document Evidence")
        evidence = plan.get("citations", []) or sources
        if evidence:
            for citation in evidence:
                st.write(f"- {citation}")
        else:
            st.write("No document citations were returned.")

        if plan.get("assumptions"):
            st.subheader("Assumptions")
            for assumption in plan["assumptions"]:
                st.write(f"- {assumption}")

    if state.get("audit_log"):
        with st.expander("Workflow Trace"):
            for entry in state["audit_log"]:
                st.write(f"- {entry}")

    accept_col, decline_col = st.columns(2)
    with accept_col:
        if st.button("Accept", use_container_width=True, type="primary"):
            with st.spinner("Recording acceptance..."):
                result = workflow.resume_human_review(
                    decision="approved",
                    thread_id=st.session_state.thread_id,
                )
            st.session_state.awaiting_review = False
            st.session_state.last_state = result
            st.session_state.thread_id = str(uuid.uuid4())
            st.rerun()
    with decline_col:
        if st.button("Decline", use_container_width=True):
            with st.spinner("Recording decline..."):
                result = workflow.resume_human_review(
                    decision="rejected",
                    thread_id=st.session_state.thread_id,
                )
            st.session_state.awaiting_review = False
            st.session_state.last_state = result
            st.session_state.thread_id = str(uuid.uuid4())
            st.rerun()

elif st.session_state.last_state:
    state = st.session_state.last_state
    status = state.get("final_status", "unknown")
    message = state.get("final_message", "")
    status_display = {
        "simulated_work_order_created": st.success,
        "rejected": st.warning,
        "escalated": st.error,
        "needs_information": st.info,
        "failed": st.error,
    }.get(status, st.info)

    st.subheader("Workflow Result")
    status_display(f"Status: {status}\n\n{message}")

    work_order = _as_dict(state.get("work_order"))
    if work_order:
        st.write(f"**Work Order ID:** {work_order.get('work_order_id')}")
        st.caption("This is a simulated record. No real treatment was scheduled.")

    if state.get("missing_information"):
        st.write("**Missing information:**")
        for item in state["missing_information"]:
            st.write(f"- {item}")

    if state.get("audit_log"):
        with st.expander("Workflow Trace"):
            for entry in state["audit_log"]:
                st.write(f"- {entry}")

    if status == "needs_information":
        st.subheader("Provide Missing Information")
        with st.form("followup_form"):
            followup = st.text_area(
                "Follow-up response",
                placeholder="Provide the missing information to continue...",
                height=100,
            )
            followup_submitted = st.form_submit_button("Continue", type="primary")

        if followup_submitted:
            if followup.strip():
                with st.spinner("Processing follow-up..."):
                    next_state = workflow.start(
                        question=followup,
                        thread_id=st.session_state.thread_id,
                    )
                _save_workflow_state(next_state)
                st.rerun()
            else:
                st.warning("Please provide the missing information before continuing.")
    elif st.button("Start new request"):
        st.session_state.last_state = None
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

else:
    fields = list_fields()
    products = list_products()
    field_labels = [f"{field.id} — {field.name}" for field in fields] + ["Other"]
    product_names = [product.name for product in products] + ["Other"]

    with st.form("treatment_form"):
        crop_choice = st.selectbox("Crop", ["Soybean", "Corn", "Wheat", "Other"])
        crop = st.text_input("Other crop") if crop_choice == "Other" else crop_choice

        product_choice = st.selectbox("Product", product_names)
        product = (
            st.text_input("Other product")
            if product_choice == "Other"
            else product_choice
        )

        state_choice = st.selectbox("State / Location", ["Missouri", "Other"])
        location = (
            st.text_input("Other state/location")
            if state_choice == "Other"
            else state_choice
        )

        field_choice = st.selectbox("Field ID", field_labels)
        field_id = (
            st.text_input("Other field ID")
            if field_choice == "Other"
            else field_choice.split(" — ", maxsplit=1)[0]
        )

        acreage = st.number_input(
            "Acreage (acres)",
            min_value=0.0,
            step=1.0,
            help="Leave at 0 to treat the field's full recorded acreage.",
        )
        application_rate = st.text_input(
            "Application Rate (fl oz/acre)",
            placeholder="e.g. 32",
            help="Leave blank to use the product label's default rate.",
        )
        treatment_date = st.date_input(
            "Treatment Date",
            min_value=date.today(),
            max_value=date.today() + timedelta(days=FORECAST_HORIZON_DAYS),
            help=(
                "The forecast the compliance checks rely on reaches about "
                f"{FORECAST_HORIZON_DAYS} days ahead."
            ),
        )
        question = st.text_area(
            "Treatment Request",
            placeholder="Describe the observed issue and requested treatment.",
            height=120,
        )
        submitted = st.form_submit_button("Submit", type="primary")

    if submitted:
        parsed_rate: float | None = None
        rate_error = False
        if application_rate.strip():
            try:
                parsed_rate = float(application_rate)
                rate_error = parsed_rate <= 0
            except ValueError:
                rate_error = True

        missing = [
            label
            for label, value in (
                ("crop", crop),
                ("product", product),
                ("field ID", field_id),
                ("treatment request", question),
            )
            if not value.strip()
        ]
        if missing:
            st.warning(f"Please provide: {', '.join(missing)}.")
        elif rate_error:
            st.warning("Application rate must be a number greater than zero.")
        else:
            workflow_request = _build_request(
                crop=crop,
                product=product,
                state=location,
                field_id=field_id,
                acreage=acreage,
                application_rate=application_rate,
                treatment_date=treatment_date.isoformat(),
                question=question,
            )
            with st.spinner("Processing request..."):
                next_state = workflow.start(
                    question=workflow_request,
                    thread_id=st.session_state.thread_id,
                )
            _save_workflow_state(next_state)
            st.rerun()

st.divider()
st.subheader("Simulated Work Order Queue")
st.caption("All records are simulated. No real treatments have been scheduled.")

orders = get_all_work_orders()
if not orders:
    st.info("No work orders have been created yet.")
else:
    for order in orders:
        with st.expander(
            f"{order['work_order_id']} — {order['field_id']} / "
            f"{order['product_name']} / {order['treatment_date']}"
        ):
            order_col1, order_col2 = st.columns(2)
            with order_col1:
                st.write(f"**Field:** {order['field_id']}")
                st.write(f"**Product:** {order['product_name']}")
                st.write(f"**Date:** {order['treatment_date']}")
            with order_col2:
                st.write(f"**Application Rate:** {order['proposed_rate']} fl oz/acre")
                st.write(f"**Acreage:** {order['treated_acres']} acres")
                st.write(f"**Created:** {order['created_at']}")
            st.caption(order["message"])
