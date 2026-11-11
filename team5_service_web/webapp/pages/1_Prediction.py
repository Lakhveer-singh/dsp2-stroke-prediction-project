import math

import pandas as pd
import requests
import streamlit as st

from utils.api_client import post_predict

st.set_page_config(page_title="Prediction", page_icon="🩺")


def to_dataframe(response: dict) -> pd.DataFrame:
    """Prediction rows + the version of the model that produced them (changes after retraining)."""
    df = pd.DataFrame(response["results"])
    df["model_version"] = response["model_version"]
    return df


st.title("Prediction")

if "prediction_result" not in st.session_state:
    st.session_state["prediction_result"] = None

st.subheader("Single prediction")

with st.form("single_prediction_form"):
    col1, col2 = st.columns(2)
    with col1:
        gender = st.selectbox("Gender", ["Male", "Female", "Other"])
        age = st.number_input("Age", min_value=0.0, max_value=120.0, value=40.0)
        hypertension = st.radio("Hypertension", [0, 1], format_func=lambda v: "Yes" if v else "No")
        heart_disease = st.radio("Heart disease", [0, 1], format_func=lambda v: "Yes" if v else "No")
        ever_married = st.selectbox("Ever married", ["Yes", "No"])
    with col2:
        work_type = st.selectbox(
            "Work type", ["Private", "Self-employed", "Govt_job", "children", "Never_worked"]
        )
        residence_type = st.selectbox("Residence type", ["Urban", "Rural"])
        avg_glucose_level = st.number_input("Average glucose level", min_value=0.01, value=90.0)
        bmi_unknown = st.checkbox("BMI unknown")
        bmi = None if bmi_unknown else st.number_input("BMI", min_value=0.01, value=25.0)
        smoking_status = st.selectbox(
            "Smoking status", ["formerly smoked", "never smoked", "smokes", "Unknown"]
        )

    submitted = st.form_submit_button("Predict")

if submitted:
    feature = {
        "gender": gender,
        "age": age,
        "hypertension": hypertension,
        "heart_disease": heart_disease,
        "ever_married": ever_married,
        "work_type": work_type,
        "residence_type": residence_type,
        "avg_glucose_level": avg_glucose_level,
        "bmi": bmi,
        "smoking_status": smoking_status,
    }
    try:
        response = post_predict([feature], source="webapp")
        st.session_state["prediction_result"] = to_dataframe(response)
    except requests.exceptions.RequestException as exc:
        st.error(f"Model service unavailable: {exc}")

st.subheader("Batch prediction (CSV upload)")
uploaded_file = st.file_uploader("Upload a CSV file with feature columns (no labels)", type="csv")

if uploaded_file is not None:
    try:
        batch_df = pd.read_csv(uploaded_file)
    except Exception as exc:
        st.warning(f"Could not read the uploaded CSV: {exc}")
        batch_df = None

    if batch_df is not None and batch_df.empty:
        st.warning("The uploaded file is empty.")
    elif batch_df is not None:
        batch_df = batch_df.rename(columns={"Residence_type": "residence_type"})
        if "id" in batch_df.columns:
            batch_df = batch_df.drop(columns=["id"])
        records = batch_df.to_dict(orient="records")
        for record in records:
            for key, value in record.items():
                if isinstance(value, float) and math.isnan(value):
                    record[key] = None

        if st.button("Predict batch"):
            try:
                response = post_predict(records, source="webapp")
                st.session_state["prediction_result"] = to_dataframe(response)
            except requests.exceptions.RequestException as exc:
                st.error(f"Model service unavailable: {exc}")

if st.session_state["prediction_result"] is not None:
    st.subheader("Results")
    st.dataframe(st.session_state["prediction_result"])
