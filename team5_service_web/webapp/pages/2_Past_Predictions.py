from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

from utils.api_client import get_past_predictions

st.set_page_config(page_title="Past Predictions", page_icon="🩺")
st.title("Past Predictions")

col1, col2, col3 = st.columns(3)
with col1:
    start_date = st.date_input("Start date", value=date.today() - timedelta(days=7))
with col2:
    end_date = st.date_input("End date", value=date.today())
with col3:
    source = st.selectbox("Source", ["all", "webapp", "scheduled"])

if st.button("Load predictions"):
    try:
        response = get_past_predictions(start_date=start_date, end_date=end_date, source=source)
    except requests.exceptions.RequestException as exc:
        st.error(f"Model service unavailable: {exc}")
    else:
        if response["count"] == 0:
            st.info("No predictions found for the selected filters.")
        else:
            st.dataframe(pd.DataFrame(response["results"]))
