"""Microsoft Teams alerting shared by the DAGs.

Two channels are used (Defense 2):
  * ``Data Quality Alerts`` -> Airflow Variable ``teams_dq_webhook_url``
  * ``ML Alerts``           -> Airflow Variable ``teams_ml_webhook_url``
(Grafana alert rules use their own contact points, see team6_monitoring.)

Payload = Adaptive Card inside a ``message`` envelope, which is what Teams "Workflows"
webhooks (and legacy incoming webhooks) accept.
"""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DQ_WEBHOOK_VARIABLE = "teams_dq_webhook_url"
ML_WEBHOOK_VARIABLE = "teams_ml_webhook_url"

_COLORS = {"info": "Good", "warning": "Warning", "critical": "Attention"}


def build_adaptive_card(title: str, facts: dict, severity: str = "warning", link_url: Optional[str] = None,
                        link_title: str = "Open report") -> dict:
    body = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium",
         "color": _COLORS.get(severity, "Default"), "wrap": True},
        {"type": "FactSet", "facts": [{"title": str(k), "value": str(v)} for k, v in facts.items()]},
    ]
    content = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }
    if link_url:
        content["actions"] = [{"type": "Action.OpenUrl", "title": link_title, "url": link_url}]
    return {
        "type": "message",
        "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": content}],
    }


def send_teams_alert(variable_name: str, title: str, facts: dict, severity: str = "warning",
                     link_url: Optional[str] = None, link_title: str = "Open report") -> bool:
    """Post an alert. Returns True if sent. Never raises: alerting must not break a DAG run."""
    from airflow.sdk import Variable  # imported lazily: this module is also imported by unit tests

    webhook_url = Variable.get(variable_name, default=None)
    if not webhook_url:
        logger.info("Variable %s not set -- skipping Teams alert: %s", variable_name, title)
        return False
    try:
        response = requests.post(
            webhook_url, json=build_adaptive_card(title, facts, severity, link_url, link_title), timeout=10
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Teams alert failed (%s): %s", variable_name, exc)
        return False
