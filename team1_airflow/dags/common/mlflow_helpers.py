"""Thin wrapper around the MLflow client used by the training DAG and the bootstrap script."""
import os
from typing import Dict, Optional

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MODEL_NAME = os.environ.get("MODEL_NAME", "stroke_model")
CHAMPION_ALIAS = os.environ.get("MODEL_ALIAS", "champion")
EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT_NAME", "stroke_prediction")


def configure() -> MlflowClient:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)
    return MlflowClient(tracking_uri=MLFLOW_TRACKING_URI, registry_uri=MLFLOW_TRACKING_URI)


def version_label(version) -> str:
    """Label stored in predictions.model_version / training_stats.model_version."""
    return f"{MODEL_NAME}_v{version}"


def get_champion_version(client: MlflowClient):
    """Current champion ModelVersion, or None if the alias does not exist yet."""
    try:
        return client.get_model_version_by_alias(MODEL_NAME, CHAMPION_ALIAS)
    except MlflowException as exc:
        if exc.error_code == "RESOURCE_DOES_NOT_EXIST":
            return None
        raise


def load_version(version):
    return mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{version}")


def log_and_register_model(pipeline, params: Dict, metrics: Dict, sample_input, run_name: str,
                           tags: Optional[Dict] = None) -> Dict:
    """Log params/metrics/model to a new run and register it as a new model version."""
    with mlflow.start_run(run_name=run_name, tags=tags or {}) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        signature = infer_signature(sample_input, pipeline.predict(sample_input))
        info = mlflow.sklearn.log_model(
            pipeline, name="model", signature=signature, registered_model_name=MODEL_NAME,
            # MLflow >= 3.? defaults to the "skops" format (extra dependency, trusted-type lists);
            # cloudpickle needs nothing beyond what mlflow-skinny already installs.
            serialization_format="cloudpickle",
        )
    version = info.registered_model_version
    return {"run_id": run.info.run_id, "model_version": int(version), "model_label": version_label(version)}


def log_to_run(run_id: str, metrics: Optional[Dict] = None, params: Optional[Dict] = None,
               tags: Optional[Dict] = None) -> None:
    """Append evaluation results to an already finished training run."""
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    for key, value in (metrics or {}).items():
        client.log_metric(run_id, key, value)
    for key, value in (params or {}).items():
        client.log_param(run_id, key, value)
    for key, value in (tags or {}).items():
        client.set_tag(run_id, key, value)


def set_champion(client: MlflowClient, version) -> None:
    client.set_registered_model_alias(MODEL_NAME, CHAMPION_ALIAS, str(version))
