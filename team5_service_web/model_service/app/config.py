import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dsp_user:change_me@localhost:5432/dsp_app")

# Fallback model: bundled pickle, only used when the MLflow registry has no champion
# (or is unreachable) at startup. Defense 1 behaviour is preserved this way.
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(os.path.dirname(__file__), "artifacts", "model_pipeline.pkl"))

# Defense 2: the model is served from the MLflow Model Registry
# (models:/<MODEL_NAME>@<MODEL_ALIAS>). Leave MLFLOW_TRACKING_URI empty to disable MLflow.
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
MODEL_NAME = os.getenv("MODEL_NAME", "stroke_model")
MODEL_ALIAS = os.getenv("MODEL_ALIAS", "champion")
MLFLOW_STARTUP_RETRIES = int(os.getenv("MLFLOW_STARTUP_RETRIES", "10"))
MLFLOW_STARTUP_RETRY_DELAY_S = float(os.getenv("MLFLOW_STARTUP_RETRY_DELAY_S", "3"))
