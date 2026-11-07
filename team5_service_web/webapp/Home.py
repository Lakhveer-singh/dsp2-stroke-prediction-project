import streamlit as st

st.set_page_config(page_title="DSP Stroke Prediction", page_icon="🩺")

st.title("Stroke Prediction")
st.write(
    "Use the sidebar to navigate:\n"
    "- **Prediction**: make a single or batch stroke-risk prediction\n"
    "- **Past Predictions**: browse previously made predictions"
)
