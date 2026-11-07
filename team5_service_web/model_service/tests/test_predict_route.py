import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app

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
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # The app's lifespan calls Base.metadata.create_all(bind=engine) against the
    # module-level engine (configured from DATABASE_URL) on startup -- point it at
    # the in-memory test engine so tests don't require a real Postgres instance.
    monkeypatch.setattr("app.main.engine", engine)

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


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_predict_single(client):
    response = client.post("/predict", json={"features": [VALID_FEATURES], "source": "webapp"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["prediction"] in (0, 1)


def test_predict_empty_features_returns_400(client):
    response = client.post("/predict", json={"features": [], "source": "webapp"})
    assert response.status_code == 400


def test_predict_invalid_gender_returns_422(client):
    bad_features = dict(VALID_FEATURES, gender="Unknown")
    response = client.post("/predict", json={"features": [bad_features], "source": "webapp"})
    assert response.status_code == 422


def test_past_predictions_filters_by_source(client):
    client.post("/predict", json={"features": [VALID_FEATURES], "source": "webapp"})
    client.post("/predict", json={"features": [VALID_FEATURES], "source": "scheduled"})

    response = client.get("/past-predictions", params={"source": "scheduled"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["source"] == "scheduled"


def test_past_predictions_empty_is_valid_200(client):
    response = client.get("/past-predictions", params={"source": "webapp"})
    assert response.status_code == 200
    assert response.json() == {"count": 0, "results": []}
