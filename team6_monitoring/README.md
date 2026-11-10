# team6_monitoring — Grafana dashboards, alerts, provisioning

Everything is **code**: Grafana loads it at start-up from `grafana/` (mounted read-only by `docker-compose.yml`).

```
grafana/
  provisioning/datasources/postgres.yaml   PostgreSQL datasource (uid dsp-postgres)
  provisioning/dashboards/dashboards.yaml  loads grafana/dashboards/*.json into folder "DSP"
  provisioning/alerting/contact-points.yaml  teams-data-quality, teams-ml (webhooks from .env)
  provisioning/alerting/policies.yaml        route by label team=data_quality | team=ml
  provisioning/alerting/rules.yaml           6 alert rules (GENERATED)
  dashboards/data_quality.json               (GENERATED)
  dashboards/drift_and_predictions.json      (GENERATED)
tools/build_monitoring.py   single source of truth for every panel / alert SQL query
tests/                      runs all SQL against a real PostgreSQL (healthy, bad-data and drift scenarios)
```

**Change a panel or alert:** edit `tools/build_monitoring.py`, run `python tools/build_monitoring.py`, run the tests
(`MONITORING_TEST_DB_URL=postgresql://… pytest team6_monitoring/tests`), commit the regenerated files (CI fails if they
are out of sync with the generator).

Data used: `predictions` (features, prediction, probability, model_version), `ingestion_stats`, `ingestion_error_types`,
`training_stats` (`is_baseline = true` rows = champion's training distribution).
