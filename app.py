import streamlit as st

st.set_page_config(page_title="AgriFlow AI", layout="wide")

st.title("AgriFlow AI")
st.write("Submit a field treatment request and review the recommendation.")

with st.form("treatment_form"):
    crop_choice = st.selectbox("Crop", ["Corn", "Soybeans", "Wheat", "Other"])
    if crop_choice == "Other":
        crop = st.text_input("Other crop")
    else:
        crop = crop_choice

    product_choice = st.selectbox("Product", ["Atrazine", "Glyphosate", "Dicamba", "Other"])
    if product_choice == "Other":
        product = st.text_input("Other product")
    else:
        product = product_choice

    state_choice = st.selectbox(
        "State / Location",
        [
            "Alabama", "Alaska", "Arizona", "Arkansas", "California",
            "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
            "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
            "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
            "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
            "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
            "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
            "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
            "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
            "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
            "Other"
        ]
    )
    if state_choice == "Other":
        state = st.text_input("Other state/location")
    else:
        state = state_choice

    field_choice = st.selectbox("Field ID", ["Field A", "Field B", "Field C", "Other"])
    if field_choice == "Other":
        field_id = st.text_input("Other field ID")
    else:
        field_id = field_choice

    acreage = st.number_input("Acreage", min_value=0.0, step=1.0)
    application_rate = st.text_input("Application Rate")

    treatment_date = st.date_input("Treatment Date")
    question = st.text_area("Treatment Request")

    submitted = st.form_submit_button("Submit")

if submitted:
    mock_response = {
        "status": "Needs Human Review",
        "recommendation": "Delay application because rain is forecast within 6 hours.",
        "weather": "Rain expected in 6 hours, wind acceptable.",
        "documents": [
            "Atrazine label: Do not apply if rain is expected within 8 hours."
        ],
        "farm_records": [
            "Field B treated with Product Y 5 days ago."
        ],
        "trace": [
            "Intake Agent",
            "Product Lookup Agent",
            "Weather Agent",
            "Farm Records Agent",
            "Compliance Agent",
            "Human Review"
        ],
        "ticket": {
            "id": "TICKET-1042",
            "status": "Pending Review",
            "reason": "Rain is forecast within 6 hours and the product restrictions require manual approval.",
            "assigned_to": "Agronomy Reviewer",
            "next_step": "Review evidence and approve, deny, or request revision."
        }
    }

    st.subheader("Request Summary")
    st.write(f"**Crop:** {crop}")
    st.write(f"**Product:** {product}")
    st.write(f"**State / Location:** {state}")
    st.write(f"**Field ID:** {field_id}")
    st.write(f"**Acreage:** {acreage}")
    st.write(f"**Application Rate:** {application_rate}")
    st.write(f"**Treatment Date:** {treatment_date}")
    st.write(f"**Treatment Request:** {question}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Recommendation")
        st.write(f"**Status:** {mock_response['status']}")
        st.write(mock_response["recommendation"])

        st.subheader("Weather Summary")
        st.write(mock_response["weather"])

        st.subheader("Farm Records")
        for record in mock_response["farm_records"]:
            st.write(f"- {record}")

    with col2:
        st.subheader("Document Evidence")
        for doc in mock_response["documents"]:
            st.write(f"- {doc}")

        st.subheader("Workflow Trace")
        for step in mock_response["trace"]:
            st.write(f"- {step}")

    if mock_response["status"] in ["Needs Human Review", "Escalated"]:
        st.subheader("Escalation Ticket")
        st.write(f"**Ticket ID:** {mock_response['ticket']['id']}")
        st.write(f"**Review Status:** {mock_response['ticket']['status']}")
        st.write(f"**Reason:** {mock_response['ticket']['reason']}")
        st.write(f"**Assigned To:** {mock_response['ticket']['assigned_to']}")
        st.write(f"**Next Step:** {mock_response['ticket']['next_step']}")
