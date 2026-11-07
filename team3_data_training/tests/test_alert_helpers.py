"""Teams alert payloads (dags/common/alert_helpers.py) - no Airflow or network needed."""
import sys
import types

import pytest
import requests

from dags.common import alert_helpers


class FakeVariable:
    values = {}

    @classmethod
    def get(cls, key, default=None):
        return cls.values.get(key, default)


@pytest.fixture()
def fake_airflow(monkeypatch):
    FakeVariable.values = {}
    pkg = types.ModuleType("airflow")
    sdk = types.ModuleType("airflow.sdk")
    sdk.Variable = FakeVariable
    monkeypatch.setitem(sys.modules, "airflow", pkg)
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    return FakeVariable


def test_card_contains_title_facts_and_link():
    payload = alert_helpers.build_adaptive_card(
        "Data quality alert", {"File": "a.csv", "Invalid rows": "9/10"}, severity="critical",
        link_url="http://localhost:8081/validations/x.html", link_title="Open Data Docs report")
    assert payload["type"] == "message"
    card = payload["attachments"][0]["content"]
    assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert card["type"] == "AdaptiveCard"
    assert card["body"][0]["text"] == "Data quality alert" and card["body"][0]["color"] == "Attention"
    assert {"title": "File", "value": "a.csv"} in card["body"][1]["facts"]
    assert card["actions"] == [{"type": "Action.OpenUrl", "title": "Open Data Docs report",
                                "url": "http://localhost:8081/validations/x.html"}]


def test_card_without_link_has_no_actions():
    card = alert_helpers.build_adaptive_card("t", {"a": 1})["attachments"][0]["content"]
    assert "actions" not in card


def test_two_distinct_channels_are_configured():
    assert alert_helpers.DQ_WEBHOOK_VARIABLE != alert_helpers.ML_WEBHOOK_VARIABLE


def test_alert_is_posted_to_the_requested_channel(fake_airflow, monkeypatch):
    fake_airflow.values = {alert_helpers.ML_WEBHOOK_VARIABLE: "http://ml.example/hook",
                           alert_helpers.DQ_WEBHOOK_VARIABLE: "http://dq.example/hook"}
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return types.SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(requests, "post", fake_post)
    assert alert_helpers.send_teams_alert(alert_helpers.ML_WEBHOOK_VARIABLE, "Promotion failed", {"r": "x"})
    assert calls[0][0] == "http://ml.example/hook"  # NOT the data-quality channel
    assert len(calls) == 1


def test_missing_webhook_is_skipped_silently(fake_airflow, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("must not post without a webhook"))
    assert alert_helpers.send_teams_alert(alert_helpers.DQ_WEBHOOK_VARIABLE, "t", {}) is False


def test_empty_webhook_string_is_skipped(fake_airflow, monkeypatch):
    fake_airflow.values = {alert_helpers.DQ_WEBHOOK_VARIABLE: ""}
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("must not post"))
    assert alert_helpers.send_teams_alert(alert_helpers.DQ_WEBHOOK_VARIABLE, "t", {}) is False


def test_network_failure_never_raises(fake_airflow, monkeypatch):
    fake_airflow.values = {alert_helpers.DQ_WEBHOOK_VARIABLE: "http://dq.example/hook"}

    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", boom)
    assert alert_helpers.send_teams_alert(alert_helpers.DQ_WEBHOOK_VARIABLE, "t", {}) is False
