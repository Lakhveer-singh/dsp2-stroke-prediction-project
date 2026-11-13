"""One-shot bootstrap: make sure the MLflow registry has a ``champion`` before the API starts.

Run by the ``mlflow-bootstrap`` compose service (Airflow image, so it has the exact same
scikit-learn / pandas / mlflow versions as the training DAG and the API):

  1. wait for the MLflow server
  2. if ``models:/stroke_model@champion`` already exists -> nothing to do (idempotent)
  3. otherwise train the baseline model on the reference dataset's training part (same
     pipeline as the Defense 1 notebook), register it as version 1, alias it ``champion`` and
     store its training statistics as the initial drift baseline.
"""
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db_helpers, mlflow_helpers, training_helpers  # noqa: E402
from common.simple_hook import SimpleHook  # noqa: E402

REFERENCE_DATASET_PATH = os.environ.get(
    "REFERENCE_DATASET_PATH", "/opt/airflow/reference/healthcare-dataset-stroke-data.xls"
)
APP_DB_URL = os.environ.get("AIRFLOW_CONN_DSP_APP_DB", "")


def wait_for_mlflow(timeout_s: int = 180) -> None:
    deadline = time.time() + timeout_s
    while True:
        try:
            if requests.get(f"{mlflow_helpers.MLFLOW_TRACKING_URI}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        if time.time() > deadline:
            raise TimeoutError("MLflow server did not become healthy in time")
        time.sleep(3)


def main() -> int:
    wait_for_mlflow()
    client = mlflow_helpers.configure()

    champion = mlflow_helpers.get_champion_version(client)
    if champion is not None:
        print(f"[bootstrap] champion already exists (version {champion.version}) -- nothing to do")
        return 0

    print("[bootstrap] no champion yet -> training the baseline model")
    datasets = training_helpers.build_datasets(REFERENCE_DATASET_PATH, good_dir="", files=None)
    train_df, test_df = datasets["train"], datasets["test"]
    pipeline = training_helpers.train_pipeline(train_df)
    metrics = training_helpers.evaluate_model(pipeline, test_df)

    registered = mlflow_helpers.log_and_register_model(
        pipeline,
        params={**datasets["info"], "note": "baseline model trained by bootstrap on reference data"},
        metrics={f"test_{k}": v for k, v in metrics.items()},
        sample_input=train_df[training_helpers.FEATURE_COLUMNS].head(50),
        run_name="bootstrap_baseline",
        tags={"trigger": "bootstrap"},
    )
    mlflow_helpers.set_champion(client, registered["model_version"])

    hook = SimpleHook(APP_DB_URL)
    stats = training_helpers.compute_training_stats(train_df, pipeline)
    db_helpers.insert_training_stats(registered["model_label"], stats, hook=hook)
    db_helpers.mark_baseline(registered["model_label"], hook=hook)
    print(f"[bootstrap] registered {registered['model_label']} as @champion; test metrics: {metrics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
