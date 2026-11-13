import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config
from app.database import get_db
from app.main import app
from app.model_registry import ModelHolder, NoChampionError, RegistryUnavailable

VALID_FEATURES = {
    "gender": "Male",
    "age": 67,
    "hypertension": 0,
    "heart_disease": 1,
    "ever_married": "Yes",
    "work_type": "Private",
    "residence_type": "Urban",
    "avg_glucose_level": 228.69,
    "bmi": 36.6,
    "smoking_status": "formerly smoked",
}


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.main.engine", engine)
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "")  # tests never talk to a real MLflow

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_model_info_reports_bundled_file_when_mlflow_disabled(client):
    body = client.get("/model-info").json()
    assert body == {"model_version": "model_pipeline.pkl", "origin": "file"}


def test_reload_without_mlflow_configured_returns_502(client):
    response = client.post("/reload-model")
    assert response.status_code == 502
    assert "not configured" in response.json()["detail"]


def test_reload_swaps_model_and_version(client, monkeypatch):
    current_model, _ = client.app.state.model_holder.get()
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setattr("app.model_registry.load_champion", lambda *a, **k: (current_model, "stroke_model_v2"))

    response = client.post("/reload-model")

    assert response.status_code == 200
    assert response.json() == {
        "status": "reloaded",
        "previous_model_version": "model_pipeline.pkl",
        "model_version": "stroke_model_v2",
    }
    assert client.get("/model-info").json() == {"model_version": "stroke_model_v2", "origin": "mlflow"}


def test_predictions_after_reload_are_labelled_with_new_version(client, monkeypatch):
    current_model, _ = client.app.state.model_holder.get()
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setattr("app.model_registry.load_champion", lambda *a, **k: (current_model, "stroke_model_v7"))

    before = client.post("/predict", json={"features": [VALID_FEATURES], "source": "webapp"}).json()
    client.post("/reload-model")
    after = client.post("/predict", json={"features": [VALID_FEATURES], "source": "webapp"}).json()

    assert before["model_version"] == "model_pipeline.pkl"
    assert after["model_version"] == "stroke_model_v7"
    stored = client.get("/past-predictions").json()["results"]
    assert {row["model_version"] for row in stored} == {"model_pipeline.pkl", "stroke_model_v7"}


def test_reload_returns_404_when_no_champion(client, monkeypatch):
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "http://mlflow:5000")

    def no_champion(*a, **k):
        raise NoChampionError("no 'champion' alias found")

    monkeypatch.setattr("app.model_registry.load_champion", no_champion)
    response = client.post("/reload-model")
    assert response.status_code == 404


def test_failed_reload_keeps_serving_previous_model(client, monkeypatch):
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "http://mlflow:5000")

    def broken(*a, **k):
        raise RegistryUnavailable("connection refused")

    monkeypatch.setattr("app.model_registry.load_champion", broken)
    assert client.post("/reload-model").status_code == 502
    assert client.get("/model-info").json()["model_version"] == "model_pipeline.pkl"
    assert client.post("/predict", json={"features": [VALID_FEATURES], "source": "webapp"}).status_code == 200


def test_initialize_falls_back_to_file_when_no_champion(monkeypatch):
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "http://mlflow:5000")

    def no_champion(*a, **k):
        raise NoChampionError("none")

    monkeypatch.setattr("app.model_registry.load_champion", no_champion)
    holder = ModelHolder()
    holder.initialize()
    assert holder.version == "model_pipeline.pkl"
    assert holder.origin == "file"


def test_initialize_retries_then_falls_back_when_registry_down(monkeypatch):
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setattr(config, "MLFLOW_STARTUP_RETRIES", 3)
    monkeypatch.setattr(config, "MLFLOW_STARTUP_RETRY_DELAY_S", 0)
    calls = {"n": 0}

    def down(*a, **k):
        calls["n"] += 1
        raise RegistryUnavailable("down")

    monkeypatch.setattr("app.model_registry.load_champion", down)
    holder = ModelHolder()
    holder.initialize()
    assert calls["n"] == 3
    assert holder.origin == "file"


def test_initialize_prefers_champion_when_available(monkeypatch):
    monkeypatch.setattr(config, "MLFLOW_TRACKING_URI", "http://mlflow:5000")
    sentinel = object()
    monkeypatch.setattr("app.model_registry.load_champion", lambda *a, **k: (sentinel, "stroke_model_v1"))
    holder = ModelHolder()
    holder.initialize()
    assert holder.get() == (sentinel, "stroke_model_v1")
    assert holder.origin == "mlflow"
