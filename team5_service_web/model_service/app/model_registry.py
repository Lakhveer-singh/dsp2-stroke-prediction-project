"""Model loading / hot-reloading from the MLflow Model Registry.

The API serves whatever model version currently carries the ``champion`` alias in the
registry. ``ModelHolder`` keeps the loaded model and its version label together behind a
lock so a ``POST /reload-model`` can swap both atomically while /predict requests are
being served (no restart needed).
"""
import logging
import threading
import time
from typing import Optional, Tuple

from app import config
from app.ml_model import load_model

logger = logging.getLogger(__name__)


class RegistryUnavailable(Exception):
    """The MLflow tracking server / registry could not be reached or returned an error."""


class NoChampionError(Exception):
    """The registry is reachable but no model version carries the champion alias."""


def load_champion(tracking_uri: str, model_name: str, alias: str) -> Tuple[object, str]:
    """Load the model version behind ``models:/<model_name>@<alias>``.

    Returns ``(sklearn_pipeline, version_label)`` where the label looks like
    ``stroke_model_v3`` and is what gets stored in ``predictions.model_version``.
    """
    import mlflow
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri, registry_uri=tracking_uri)
    try:
        model_version = client.get_model_version_by_alias(model_name, alias)
    except MlflowException as exc:
        if exc.error_code == "RESOURCE_DOES_NOT_EXIST":
            raise NoChampionError(f"no '{alias}' alias found for registered model '{model_name}'") from exc
        raise RegistryUnavailable(str(exc)) from exc
    except Exception as exc:  # connection errors, timeouts, ...
        raise RegistryUnavailable(str(exc)) from exc

    try:
        # Pin the exact version we just resolved so the label always matches the model.
        model = mlflow.sklearn.load_model(f"models:/{model_name}/{model_version.version}")
    except Exception as exc:
        raise RegistryUnavailable(f"could not load {model_name} v{model_version.version}: {exc}") from exc
    return model, f"{model_name}_v{model_version.version}"


class ModelHolder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model: Optional[object] = None
        self._version: Optional[str] = None
        self._origin: str = "none"

    def get(self) -> Tuple[object, str]:
        with self._lock:
            return self._model, self._version

    @property
    def version(self) -> Optional[str]:
        with self._lock:
            return self._version

    @property
    def origin(self) -> str:
        with self._lock:
            return self._origin

    def set(self, model: object, version: str, origin: str) -> None:
        with self._lock:
            self._model, self._version, self._origin = model, version, origin

    def load_fallback_file(self) -> None:
        import os

        self.set(load_model(config.MODEL_PATH), os.path.basename(config.MODEL_PATH), "file")

    def reload_from_registry(self) -> Tuple[Optional[str], str]:
        """Swap in the current champion. Returns ``(previous_version, new_version)``.

        The old model keeps serving if loading fails: nothing is swapped until the new
        model has been fully loaded.
        """
        if not config.MLFLOW_TRACKING_URI:
            raise RegistryUnavailable("MLFLOW_TRACKING_URI is not configured")
        previous = self.version
        model, version = load_champion(config.MLFLOW_TRACKING_URI, config.MODEL_NAME, config.MODEL_ALIAS)
        self.set(model, version, "mlflow")
        logger.info("Model reloaded: %s -> %s", previous, version)
        return previous, version

    def initialize(self) -> None:
        """Startup: champion from MLflow if possible, otherwise the bundled pickle."""
        if config.MLFLOW_TRACKING_URI:
            for attempt in range(1, config.MLFLOW_STARTUP_RETRIES + 1):
                try:
                    self.reload_from_registry()
                    return
                except NoChampionError as exc:
                    logger.warning("%s -- falling back to bundled model file", exc)
                    break
                except RegistryUnavailable as exc:
                    logger.warning("MLflow unavailable (attempt %d/%d): %s", attempt,
                                   config.MLFLOW_STARTUP_RETRIES, exc)
                    time.sleep(config.MLFLOW_STARTUP_RETRY_DELAY_S)
            else:
                logger.warning("MLflow never became available -- falling back to bundled model file")
        self.load_fallback_file()
