import math
import os
from datetime import datetime

import pandas as pd
import requests
from airflow.exceptions import AirflowSkipException
from airflow.models import Variable
from airflow.sdk import dag, task

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD_DATA_DIR = os.path.join(REPO_ROOT, "data", "good_data")
MODEL_SERVICE_URL = os.getenv("MODEL_SERVICE_URL", "http://model_service:8000")
PROCESSED_FILES_VARIABLE = "processed_good_data_files"


def _to_json_safe_records(df: pd.DataFrame) -> list:
    df = df.rename(columns={"Residence_type": "residence_type"})
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                record[key] = None
    return records


@dag(schedule="*/2 * * * *", start_date=datetime(2026, 1, 1), catchup=False, tags=["prediction"])
def prediction_dag():
    @task
    def check_for_new_data() -> list:
        processed = set(Variable.get(PROCESSED_FILES_VARIABLE, default_var=[], deserialize_json=True))
        all_files = [f for f in os.listdir(GOOD_DATA_DIR) if f.endswith(".csv")]
        new_files = sorted(f for f in all_files if f not in processed)

        if not new_files:
            # Raising here (rather than only skipping inside make_predictions) causes
            # make_predictions to be skipped too via Airflow's default trigger rule,
            # so the whole run -- not just one task -- shows as skipped.
            raise AirflowSkipException("No new files in good_data")

        return new_files

    @task
    def make_predictions(new_files: list) -> None:
        rows = []
        for file_name in new_files:
            df = pd.read_csv(os.path.join(GOOD_DATA_DIR, file_name))
            rows.extend(_to_json_safe_records(df))

        response = requests.post(
            f"{MODEL_SERVICE_URL}/predict",
            json={"features": rows, "source": "scheduled"},
            timeout=60,
        )
        response.raise_for_status()

        processed = set(Variable.get(PROCESSED_FILES_VARIABLE, default_var=[], deserialize_json=True))
        processed.update(new_files)
        Variable.set(PROCESSED_FILES_VARIABLE, sorted(processed), serialize_json=True)

    make_predictions(check_for_new_data())


prediction_dag()
