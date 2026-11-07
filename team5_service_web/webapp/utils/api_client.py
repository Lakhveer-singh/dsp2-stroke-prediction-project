import os

import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://model_service:8000")


def get_health():
    response = requests.get(f"{API_BASE_URL}/health", timeout=5)
    response.raise_for_status()
    return response.json()


def post_predict(features, source):
    response = requests.post(
        f"{API_BASE_URL}/predict",
        json={"features": features, "source": source},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_past_predictions(start_date=None, end_date=None, source="all", limit=100):
    params = {"source": source, "limit": limit}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()

    response = requests.get(f"{API_BASE_URL}/past-predictions", params=params, timeout=15)
    response.raise_for_status()
    return response.json()
