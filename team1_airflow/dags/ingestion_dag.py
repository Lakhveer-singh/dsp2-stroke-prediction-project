import io
import os
import random
import sys
from datetime import datetime

import pandas as pd
from airflow.exceptions import AirflowSkipException
from airflow.sdk import dag, task

# The DAG bundle loader does not always add this file's own directory to
# sys.path, so make the sibling "common" package importable explicitly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import alert_helpers, db_helpers, gx_helpers  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA_DIR = os.path.join(REPO_ROOT, "data", "raw_data")
GOOD_DATA_DIR = os.path.join(REPO_ROOT, "data", "good_data")
BAD_DATA_DIR = os.path.join(REPO_ROOT, "data", "bad_data")


@dag(schedule="*/1 * * * *", start_date=datetime(2026, 1, 1), catchup=False, tags=["ingestion"])
def ingestion_dag():
    @task
    def read_data() -> dict:
        files = [f for f in os.listdir(RAW_DATA_DIR) if f.endswith(".csv")]
        if not files:
            raise AirflowSkipException("No files found in raw_data")

        file_name = random.choice(files)
        file_path = os.path.join(RAW_DATA_DIR, file_name)
        with open(file_path, "r") as f:
            csv_content = f.read()
        os.remove(file_path)

        return {"file_name": file_name, "csv_content": csv_content}

    @task
    def validate_data(read_result: dict) -> dict:
        df = pd.read_csv(io.StringIO(read_result["csv_content"]))
        return gx_helpers.run_validation(df)

    @task
    def save_statistics(read_result: dict, validation_result: dict) -> None:
        stat_id = db_helpers.insert_ingestion_stat(
            source_filename=read_result["file_name"],
            criticality=validation_result["criticality"],
            total_rows=validation_result["total_rows"],
            invalid_rows=validation_result["invalid_rows"],
            invalid_percentage=validation_result["invalid_percentage"],
            missing_column=validation_result["missing_column"],
        )
        db_helpers.insert_ingestion_error_types(stat_id, validation_result["error_counts"])

    @task
    def send_alerts(read_result: dict, validation_result: dict) -> None:
        criticality = validation_result["criticality"]
        if criticality not in ("medium", "high"):
            return

        errors = ", ".join(f"{k}: {v}" for k, v in validation_result["error_counts"].items())
        if validation_result["missing_column"]:
            errors = "missing column (schema error)"
        alert_helpers.send_teams_alert(
            alert_helpers.DQ_WEBHOOK_VARIABLE,
            title=f"Data quality alert - criticality {criticality.upper()}",
            facts={
                "File": read_result["file_name"],
                "Criticality": criticality,
                "Invalid rows": f"{validation_result['invalid_rows']}/{validation_result['total_rows']} "
                                f"({validation_result['invalid_percentage']:.1f}%)",
                "Errors": errors or "-",
            },
            severity="critical" if criticality == "high" else "warning",
            link_url=validation_result["data_docs_url"],
            link_title="Open Data Docs report",
        )

    @task
    def split_and_save_data(read_result: dict, validation_result: dict) -> None:
        df = pd.read_csv(io.StringIO(read_result["csv_content"]))
        file_name = read_result["file_name"]

        os.makedirs(GOOD_DATA_DIR, exist_ok=True)
        os.makedirs(BAD_DATA_DIR, exist_ok=True)

        if validation_result["missing_column"] or validation_result["invalid_rows"] == validation_result["total_rows"]:
            df.to_csv(os.path.join(BAD_DATA_DIR, file_name), index=False)
        elif validation_result["invalid_rows"] == 0:
            df.to_csv(os.path.join(GOOD_DATA_DIR, file_name), index=False)
        else:
            invalid_indices = validation_result["invalid_row_indices"]
            bad_df = df.loc[df.index.isin(invalid_indices)]
            good_df = df.loc[~df.index.isin(invalid_indices)]
            good_df.to_csv(os.path.join(GOOD_DATA_DIR, file_name), index=False)
            bad_df.to_csv(os.path.join(BAD_DATA_DIR, file_name), index=False)

    read_result = read_data()
    validation_result = validate_data(read_result)
    save_statistics(read_result, validation_result)
    send_alerts(read_result, validation_result)
    split_and_save_data(read_result, validation_result)


ingestion_dag()
