import pandas as pd
import pytest

from dags.common.gx_helpers import run_validation


@pytest.fixture()
def clean_row():
    return {
        "gender": "Male",
        "age": 40.0,
        "hypertension": 0,
        "heart_disease": 0,
        "ever_married": "Yes",
        "work_type": "Private",
        "Residence_type": "Urban",
        "avg_glucose_level": 90.0,
        "bmi": 25.0,
        "smoking_status": "never smoked",
    }


def make_df(clean_row, n_rows=10):
    return pd.DataFrame([dict(clean_row) for _ in range(n_rows)])


def test_clean_data_has_no_errors(clean_row):
    result = run_validation(make_df(clean_row))
    assert result["criticality"] == "none"
    assert result["invalid_rows"] == 0
    assert result["error_counts"] == {}


def test_null_required_field_is_counted(clean_row):
    df = make_df(clean_row)
    df.loc[0, "gender"] = None

    result = run_validation(df)
    assert result["invalid_rows"] == 1
    assert result["error_counts"]["null_required_field"] == 1


def test_missing_column_marks_high_criticality_with_zero_invalid_rows(clean_row):
    df = make_df(clean_row).drop(columns=["smoking_status"])

    result = run_validation(df)
    assert result["missing_column"] is True
    assert result["criticality"] == "high"
    assert result["invalid_rows"] == 0


def test_error_counts_sum_matches_expected_row_level_errors(clean_row):
    df = make_df(clean_row)
    df.loc[0, "age"] = -5
    df.loc[1, "work_type"] = "Freelancer"
    df.loc[2, "bmi"] = -10.0

    result = run_validation(df)
    assert result["invalid_rows"] == 3
    assert result["error_counts"] == {
        "value_out_of_range": 1,
        "invalid_categorical_value": 1,
        "impossible_value": 1,
    }
