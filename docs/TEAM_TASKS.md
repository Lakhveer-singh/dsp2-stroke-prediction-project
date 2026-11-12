# Task split for 4 people (Defense 2)

One repository, one `docker-compose.yml`. Work is split by **feature**, each on its own `feature/*` branch (never
named after a person — course rule). Each person must be able to explain *every line* of their part (use
`DEFENSE2_GUIDE.md`) and Airflow/Docker basics. These descriptions are also the content of **slide 2** (replace the
placeholders with real names).

| # | Workstream (branch) | Owner | Main files | Must be able to explain |
|---|---|---|---|---|
| 1 | **Model registry & serving** — `feature/mlflow-model-registry` | _Person A_ | `model_service/app/model_registry.py`, `main.py`, `routers/reload_model.py`, `schemas.py`, `models_orm.py` (TrainingStat); `team2_docker_env/mlflow/`, compose services `mlflow`, `mlflow-bootstrap`; `common/bootstrap_registry.py`, `common/mlflow_helpers.py`; `team1_airflow/Dockerfile` | MLflow tracking/registry/alias; `models:/…@champion`; `/reload-model` + lock; fallback; bootstrap; `--allowed-hosts`; why same library versions in API and Airflow; custom Airflow image |
| 2 | **Training pipeline** — `feature/training-dag` | _Person B_ | `dags/training_dag.py`, `common/training_helpers.py`, `common/db_helpers.py` (training stats), `tests/test_training_helpers.py` | the 7 tasks, skip/branching, fixed test set + labels + leakage, promotion rule, metric choice, `training_stats` and `is_baseline`, archive logic, DAG params |
| 3 | **Grafana monitoring** — `feature/grafana-monitoring` | _Person C_ | `team6_monitoring/**`, `scripts/simulate_traffic.py`, compose service `grafana` | both dashboards panel by panel, drift maths (z-score, TVD), alert rules + `team` label routing, provisioning as code, how the SQL is tested, how data was generated |
| 4 | **Data Docs, alerts, CI/CD, demo & docs** — `feature/data-docs-alerts`, `feature/cd-release`, `feature/docs-demo` | _Person D_ | compose service `nginx` + `nginx/default.conf`, `common/gx_helpers.py` (URL), `common/alert_helpers.py`, `ingestion_dag.py` (`send_alerts`), `.github/**`, `scripts/generate_demo_data.py`, README/docs, slides | nginx serving Data Docs and how links are built; Adaptive-Card alerts + 2 channels; CI jobs; CD + semantic versioning; the 5 demo files; (Great Expectations questions: only the person who implemented GX in Defense 1) |

Everybody: compose file, health checks and start-up order, Airflow concepts, the end-to-end lifecycle picture.

## Suggested order of work / integration
1. #1 and #4(nginx) first — others depend on MLflow and the compose file. Merge to `develop` early.
2. #2 after #1 is merged (needs `mlflow_helpers`, `bootstrap`). #3 can start immediately on SQL (the tests need only PostgreSQL).
3. Integrate on `develop` every few days; run the full demo script once a week.
4. Last week: only bug fixes, rehearsal, slides.
