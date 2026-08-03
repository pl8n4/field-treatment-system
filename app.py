
import streamlit as st

st.set_page_config(page_title="Field Treatment System", layout="wide")

st.title("Field Treatment System")
st.write("Submit a treatment request and review the system recommendation.")

with st.form("treatment_form"):
    crop = st.text_input("Crop")
    product = st.text_input("Product")
    state = st.text_input("State / Location", value="Missouri")
    field_id = st.text_input("Field ID")
    treatment_date = st.text_input("Treatment Date")
    question = st.text_area("Question / Problem")

    submitted = st.form_submit_button("Submit")

if submitted:
    mock_response = {
        "status": "Needs Human Review",
        "recommendation": "Delay application because rain is forecast within 6 hours.",
        "weather": "Rain expected in 6 hours, wind acceptable.",
        "documents": [
            "Product X label: Do not apply if rain is expected within 8 hours."
        ],
        "farm_records": [
            "Field A treated with Product Y 5 days ago."
        ],
        "trace": [
            "Intake Agent",
            "Product Lookup Agent",
            "Weather Agent",
            "Farm Records Agent",
            "Compliance Agent",
            "Human Review"
        ]
    }

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
