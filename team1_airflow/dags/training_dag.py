"""Training DAG (Defense 2): retrain -> evaluate -> promote -> reload API -> archive data.

load_data -> train_model -> save_training_stats -> evaluate_candidate -> promote_to_champion -+-> notify_api_reload
                                                                                              +-> archive_data

* ``load_data`` skips the whole run when fewer than ``min_new_files`` new good_data files
  arrived since the last training run.
* ``promote_to_champion`` is skipped (and so are ``notify_api_reload`` / ``archive_data``)
  when the candidate fails the promotion criteria; an alert goes to the ML Alerts channel.
* All thresholds are DAG params -> they can be changed in the Airflow "Trigger DAG" form
  (handy for the demo, e.g. a tiny inference_time_threshold_ms forces a failed promotion).
"""
import os
import shutil
import sys
from datetime import datetime, timedelta

import requests
from airflow.exceptions import AirflowSkipException
from airflow.sdk import Param, Variable, dag, get_current_context, task

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import alert_helpers, db_helpers, mlflow_helpers, training_helpers  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DSP_DATA_DIR", os.path.join(REPO_ROOT, "data"))
GOOD_DATA_DIR = os.path.join(DATA_DIR, "good_data")
ARCHIVED_DATA_DIR = os.path.join(DATA_DIR, "archived_data")
REFERENCE_DATASET_PATH = os.environ.get(
    "REFERENCE_DATASET_PATH", "/opt/airflow/reference/healthcare-dataset-stroke-data.xls"
)
MODEL_SERVICE_URL = os.environ.get("MODEL_SERVICE_URL", "http://model_service:8000")

TRAINING_SEEN_FILES_VARIABLE = "training_seen_good_data_files"  # files already counted by a training run
PREDICTION_PROCESSED_VARIABLE = "processed_good_data_files"  # maintained by prediction_dag

DEFAULT_MIN_NEW_FILES = int(os.environ.get("TRAINING_MIN_NEW_FILES", "5"))
DEFAULT_PRIMARY_METRIC = os.environ.get("TRAINING_PRIMARY_METRIC", "f1")
DEFAULT_INFERENCE_THRESHOLD_MS = float(os.environ.get("TRAINING_INFERENCE_THRESHOLD_MS", "200"))
TRAINING_SCHEDULE = os.environ.get("TRAINING_SCHEDULE", "*/10 * * * *")


def _params() -> dict:
    return get_current_context()["params"]


@dag(
    schedule=TRAINING_SCHEDULE,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["training", "mlflow"],
    default_args={"retries": 1, "retry_delay": timedelta(seconds=20)},
    params={
        "min_new_files": Param(DEFAULT_MIN_NEW_FILES, type="integer", minimum=0,
                               description="New good_data files needed since the last training run"),
        "primary_metric": Param(DEFAULT_PRIMARY_METRIC, type="string", enum=list(training_helpers.PRIMARY_METRICS),
                                description="Metric used for candidate vs champion"),
        "inference_time_threshold_ms": Param(DEFAULT_INFERENCE_THRESHOLD_MS, type="number", minimum=0,
                                             description="Max mean latency of one single-row prediction (ms)"),
        "min_improvement": Param(0.0, type="number",
                                 description="Candidate must beat the champion by at least this much "
                                             "(0 = matching it is enough)"),
    },
)
def training_dag():
    @task
    def load_data() -> dict:
        params = _params()
        all_files = training_helpers.list_good_files(GOOD_DATA_DIR)
        seen = set(Variable.get(TRAINING_SEEN_FILES_VARIABLE, default=[], deserialize_json=True))
        new_files = [f for f in all_files if f not in seen]

        if not all_files or len(new_files) < params["min_new_files"]:
            raise AirflowSkipException(
                f"Only {len(new_files)} new good_data file(s) since the last training run "
                f"(need {params['min_new_files']}) -- skipping."
            )
        return {"files": all_files, "new_files": new_files}

    @task
    def train_model(load_result: dict) -> dict:
        params = _params()
        client = mlflow_helpers.configure()
        datasets = training_helpers.build_datasets(REFERENCE_DATASET_PATH, GOOD_DATA_DIR, load_result["files"])
        train_df, test_df, info = datasets["train"], datasets["test"], datasets["info"]

        pipeline = training_helpers.train_pipeline(train_df)
        metrics = training_helpers.evaluate_model(pipeline, test_df)
        champion = mlflow_helpers.get_champion_version(client)

        registered = mlflow_helpers.log_and_register_model(
            pipeline,
            params={**info, "primary_metric": params["primary_metric"],
                    "previous_champion": champion.version if champion else "none"},
            metrics={f"test_{k}": v for k, v in metrics.items()},
            sample_input=train_df[training_helpers.FEATURE_COLUMNS].head(50),
            run_name=f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            tags={"trigger": "training_dag"},
        )

        seen = set(Variable.get(TRAINING_SEEN_FILES_VARIABLE, default=[], deserialize_json=True))
        Variable.set(TRAINING_SEEN_FILES_VARIABLE, sorted(seen | set(load_result["files"])), serialize_json=True)
        return {**registered, "dataset_info": info, "candidate_test_metrics": metrics}

    @task
    def save_training_stats(train_result: dict, load_result: dict) -> int:
        datasets = training_helpers.build_datasets(REFERENCE_DATASET_PATH, GOOD_DATA_DIR, load_result["files"])
        model = mlflow_helpers.load_version(train_result["model_version"])
        stats = training_helpers.compute_training_stats(datasets["train"], model)
        # Stored as NOT baseline: only the promoted model's stats become the drift baseline.
        return db_helpers.insert_training_stats(train_result["model_label"], stats)

    @task
    def evaluate_candidate(train_result: dict, _stats_saved: int) -> dict:
        params = _params()
        client = mlflow_helpers.configure()
        test_df = training_helpers.build_datasets(REFERENCE_DATASET_PATH, GOOD_DATA_DIR, None)["test"]

        candidate = mlflow_helpers.load_version(train_result["model_version"])
        champion_version = mlflow_helpers.get_champion_version(client)
        candidate_metrics = training_helpers.evaluate_model(candidate, test_df)
        champion_metrics = None
        if champion_version is not None:
            champion_metrics = training_helpers.evaluate_model(
                mlflow_helpers.load_version(champion_version.version), test_df
            )
        inference_ms = training_helpers.measure_inference_ms(candidate, test_df)

        decision = training_helpers.decide_promotion(
            candidate_metrics, champion_metrics, params["primary_metric"], inference_ms,
            params["inference_time_threshold_ms"], params["min_improvement"],
        )
        decision.update({
            "candidate_version": train_result["model_label"],
            "champion_version": mlflow_helpers.version_label(champion_version.version) if champion_version else None,
            "candidate_metrics": candidate_metrics,
            "champion_metrics": champion_metrics,
        })

        # Always log the comparison to the candidate's MLflow run.
        logged_metrics = {f"eval_candidate_{k}": v for k, v in candidate_metrics.items()}
        logged_metrics.update({f"eval_champion_{k}": v for k, v in (champion_metrics or {}).items()})
        logged_metrics["eval_inference_ms"] = inference_ms
        mlflow_helpers.log_to_run(
            train_result["run_id"], metrics=logged_metrics,
            tags={"promotion_decision": "promoted" if decision["promote"] else "rejected",
                  "promotion_reason": decision["reason"][:250]},
        )

        if not decision["promote"]:
            alert_helpers.send_teams_alert(
                alert_helpers.ML_WEBHOOK_VARIABLE,
                title="Model promotion failed - candidate rejected",
                facts={
                    "Candidate": decision["candidate_version"],
                    "Current champion": decision["champion_version"] or "none",
                    "Reason": decision["reason"],
                    f"Candidate {decision['primary_metric']}": f"{decision['candidate_value']:.4f}",
                    f"Champion {decision['primary_metric']}": (
                        f"{decision['champion_value']:.4f}" if decision["champion_value"] is not None else "n/a"),
                    "Inference time": f"{inference_ms:.1f} ms (limit {params['inference_time_threshold_ms']:g} ms)",
                },
                severity="warning",
                link_url=f"{os.environ.get('MLFLOW_PUBLIC_URL', 'http://localhost:5000')}/#/experiments",
                link_title="Open MLflow",
            )
        return decision

    @task
    def promote_to_champion(train_result: dict, decision: dict) -> dict:
        if not decision["promote"]:
            raise AirflowSkipException(f"Not promoted: {decision['reason']}")
        client = mlflow_helpers.configure()
        mlflow_helpers.set_champion(client, train_result["model_version"])
        # Only the promoted model's training stats serve as the drift baseline.
        db_helpers.mark_baseline(train_result["model_label"])
        mlflow_helpers.log_to_run(train_result["run_id"], tags={"promoted_to_champion": "true"})
        return {"model_label": train_result["model_label"], "model_version": train_result["model_version"]}

    @task(retries=3, retry_delay=timedelta(seconds=10))
    def notify_api_reload(promotion: dict) -> dict:
        response = requests.post(f"{MODEL_SERVICE_URL}/reload-model", timeout=60)
        response.raise_for_status()
        body = response.json()
        if body["model_version"] != promotion["model_label"]:
            raise RuntimeError(f"API reloaded {body['model_version']} but expected {promotion['model_label']}")
        return body

    @task
    def archive_data(load_result: dict, promotion: dict) -> list:
        """Move the files used for training to archived_data.

        Files the prediction DAG has not scored yet stay in good_data (otherwise they would
        silently never get a prediction); they are archived by a later training run.
        """
        scored = set(Variable.get(PREDICTION_PROCESSED_VARIABLE, default=[], deserialize_json=True))
        os.makedirs(ARCHIVED_DATA_DIR, exist_ok=True)
        moved = []
        for name in load_result["files"]:
            source = os.path.join(GOOD_DATA_DIR, name)
            if name in scored and os.path.exists(source):
                shutil.move(source, os.path.join(ARCHIVED_DATA_DIR, name))
                moved.append(name)
        return moved

    loaded = load_data()
    trained = train_model(loaded)
    stats_saved = save_training_stats(trained, loaded)
    decision = evaluate_candidate(trained, stats_saved)
    promotion = promote_to_champion(trained, decision)
    notify_api_reload(promotion)
    archive_data(loaded, promotion)


training_dag()
