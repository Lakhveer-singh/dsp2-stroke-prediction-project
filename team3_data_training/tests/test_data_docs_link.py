"""Alert links must point at the nginx-served Data Docs page of the exact validation run."""
import pandas as pd
import pytest

from dags.common import gx_helpers


@pytest.mark.parametrize("site_url,expected_suffix", [
    ("file:///opt/airflow/great_expectations/gx/uncommitted/data_docs/local_site/validations/stroke_suite/"
     "__none__/20260101T000000.000000Z/pandas_ds-stroke_asset.html",
     "/validations/stroke_suite/__none__/20260101T000000.000000Z/pandas_ds-stroke_asset.html"),
    ("file:///x/local_site/index.html", "/index.html"),
])
def test_file_url_is_translated_to_the_public_nginx_url(site_url, expected_suffix):
    url = gx_helpers.to_public_url(site_url)
    assert url == gx_helpers.DATA_DOCS_PUBLIC_URL + expected_suffix
    assert "file://" not in url and "/opt/airflow" not in url


def test_unknown_location_falls_back_to_the_index_page():
    assert gx_helpers.to_public_url("something/else") == gx_helpers.DATA_DOCS_PUBLIC_URL + "/index.html"


def test_run_validation_returns_a_link_to_the_validation_report():
    row = {"gender": "Male", "age": 40.0, "hypertension": 0, "heart_disease": 0, "ever_married": "Yes",
           "work_type": "Private", "Residence_type": "Urban", "avg_glucose_level": 90.0, "bmi": 25.0,
           "smoking_status": "never smoked"}
    result = gx_helpers.run_validation(pd.DataFrame([dict(row) for _ in range(10)]))
    assert result["data_docs_url"].startswith(gx_helpers.DATA_DOCS_PUBLIC_URL + "/validations/")
    assert result["data_docs_url"].endswith(".html")
