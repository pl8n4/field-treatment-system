import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import uuid
import streamlit as st

from data_layer.work_orders import get_all_work_orders, init_db
from workflow.graph import AgriculturalWorkflow

# Initialize DB and workflow once per session
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

st.set_page_config(page_title="Field Treatment Review", layout="wide")
st.title("Field Treatment System")

tab_submit, tab_queue = st.tabs(["Submit Request", "Work Order Queue"])

# SUBMIT TAB
with tab_submit:
    
    # If waiting for human review > show the approve/reject UI
    if st.session_state.awaiting_review and st.session_state.last_state:
        state = st.session_state.last_state
        plan = state.get("plan")
        review = state.get("review")
        
        # Convert to dicts if they're Pydantic models
        if hasattr(plan, "model_dump"):
            plan = plan.model_dump()
        if hasattr(review, "model_dump"):
            review = review.model_dump()
            
        sources = state.get("context_sources", [])
        
        st.subheader("Human Review Required")
        st.info(
            "The system has drafted a treatment plan and completed compliance "
            "checks. A qualified reviewer must approve or reject before any "
            "action is taken. No treatment has been scheduled."
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Treatment Plan")
            if plan:
                st.write(f"**Field:** {plan.get('field_id')}")
                st.write(f"**Product:** {plan.get('product_name')}")
                st.write(f"**Date:** {plan.get('treatment_date')}")
                st.write(f"**Rate:** {plan.get('proposed_rate')} fl oz/acre")
                st.write(f"**Acres:** {plan.get('treated_acres')}")
                st.write("---")
                st.write(f"**Timing:** {plan.get('timing_summary')}")
                st.write(f"**Buffer:** {plan.get('buffer_summary')}")
                st.write(f"**REI:** {plan.get('rei_summary')}")
                st.write(f"**PHI:** {plan.get('phi_summary')}")
                
                if plan.get("assumptions"):
                    st.write("Assumptions:")
                    for a in plan["assumptions"]:
                        st.write(f"- {a}")
                        
                if plan.get("citations"):
                    st.write("Citations:")
                    for citation in plan["citations"]:
                        st.write(f"- {citation}")
        
        with col2:
            st.subheader("Compliance Review")
            if review:
                verdict = review.get("verdict", "unknown")
                st.write(f"Verdict: {verdict}")
                st.write(review.get("explanation", ""))
                
                if review.get("issues"):
                    st.write("Issues:")
                    for issue in review["issues"]:
                        st.write(f"- {issue}")
                        
            if sources:
                st.write("Evidence sources:")
                for source in sources:
                    st.write(f"- {source}")
            
        st.write("---")
        col_approve, col_reject = st.columns(2)
        
        with col_approve:
            if st.button("Approve", use_container_width=True, type="primary"):
                with st.spinner("Processing approval..."):
                    result = workflow.resume_human_review(
                        decision="approved",
                        thread_id=st.session_state.thread_id,
                    )
                st.session_state.awaiting_review = False
                st.session_state.last_state = result
                st.session_state.thread_id = str(uuid.uuid4())
                st.rerun()
        
        with col_reject:
            if st.button("Reject", use_container_width=True):
                with st.spinner("Processing rejection..."):
                    result = workflow.resume_human_review(
                        decision="rejected", 
                        thread_id=st.session_state.thread_id,
                    )
                st.session_state.awaiting_review = False
                st.session_state.last_state = result
                st.session_state.thread_id = str(uuid.uuid4())
                st.rerun()
        
    # Show the result of the last completed run        
    elif st.session_state.last_state:
        state = st.session_state.last_state
        status = state.get("final_status", "unknown")
        message = state.get("final_message", "")
        
        status_colors = {
            "simulated_work_order_created": "success",
            "rejected": "warning", 
            "escalated": "error",
            "needs_information": "info",
            "failed": "error",
        }
        
        display = getattr(st, status_colors.get(status, "info"))
        display(f"Status: {status}\n\n{message}")
        
        if state.get("work_order"):
            wo = state["work_order"]
            st.write(
                f"Work Order ID: {wo.work_order_id if hasattr(wo, 'work_order_id') else wo.get('work_order_id')}"
            )
            st.caption("This is a simulated record. No real treatment was scheduled.")

        if state.get("missing_information"):
            st.write("Missing information:")
            for item in state["missing_information"]:
                st.write(f"- {item}")
      
        if state.get("audit_log"):
            with st.expander("Workflow trace"):
                for entry in state["audit_log"]:
                    st.write(f"- {entry}")
                
        if status == "needs_information":
            st.write("---")
            st.subheader("Provide Missing Information")
            with st.form("followup_form"):
                followup = st.text_area(
                    "Follow-up response",
                    placeholder="Provide the missing information to continue...",
                    height=100,
                )
                followup_submitted = st.form_submit_button("Continue", type="primary")

            if followup_submitted and followup.strip():
                with st.spinner("Processing follow-up..."):
                    state = workflow.start(
                        question=followup,
                        thread_id=st.session_state.thread_id,
                    )
                interrupt_val = state.get("__interrupt__")
                if interrupt_val:
                    st.session_state.awaiting_review = True
                    st.session_state.last_state = state
                    st.rerun()
                else:
                    st.session_state.last_state = state
                    st.rerun()
        else:
            if st.button("Start new request"):
                st.session_state.last_state = None
                st.session_state.thread_id = str(uuid.uuid4())
                st.rerun()
    
    # Default: Show submission form
    else:
        st.subheader("Submit a Treatment Request")
        st.write("Describe the field issue and proposed treatment in plain language.")
        
        with st.form("treatment_form"):
            question = st.text_area(
                "Request",
                placeholder=(
                    'e.g. "Field F-02 has waterhemp. Apply Enlist One on '
                    '2026-08-10 at 32 fl oz/acre across 80 acres."'
                ),
                height=120,
            )
            submitted = st.form_submit_button("Submit", type="primary")
            
        if submitted and question.strip():
            with st.spinner("Processing request..."):
                state = workflow.start(
                    question=question,
                    thread_id=st.session_state.thread_id,
                )
                
            interrupt_val = state.get("__interrupt__")
            
            if interrupt_val:
                st.session_state.awaiting_review = True
            
            st.session_state.last_state = state
            st.rerun()
        
        elif submitted:
            st.warning("Please enter a request before submitting.")
            
# WORK ORDER QUEUE TAB
with tab_queue:
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
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Field:** {order['field_id']}")
                    st.write(f"**Product:** {order['product_name']}")
                    st.write(f"**Date:** {order['treatment_date']}")
                with col2:
                    st.write(f"**Rate:** {order['proposed_rate']} fl oz/acre")
                    st.write(f"**Acres:** {order['treated_acres']}")
                    st.write(f"**Created:** {order['created_at']}")
                st.caption(order["message"])