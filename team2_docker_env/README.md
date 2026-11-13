# team2_docker_env — orchestration (Docker Compose)

Everything runs from **one** `docker-compose.yml`. Main documentation: [`../README.md`](../README.md).

## Services

| Service | Image / build | Purpose | Host port |
|---|---|---|---|
| `db` | `postgres:16` | one instance, 3 databases: `dsp_app`, `airflow`, `mlflow` | – |
| `mlflow` | `./mlflow` (python + mlflow 3.17.2) | tracking server, model registry, artifact proxy (`./mlflow-artifacts`) | 5000 |
| `mlflow-bootstrap` | Airflow image | one-shot: registers baseline model v1 as `@champion` + initial drift baseline | – |
| `model_service` | `../team5_service_web/model_service` | FastAPI, serves `models:/stroke_model@champion` | internal |
| `webapp` | `../team5_service_web/webapp` | Streamlit | 8501 |
| `airflow-init`, `airflow-apiserver`, `airflow-scheduler`, `airflow-dag-processor` | `dsp-airflow:2.0` (`../team1_airflow/Dockerfile`) | Airflow 3.1 | 8080 |
| `nginx` | `nginx:1.27-alpine` | serves the Great Expectations Data Docs | 8081 |
| `grafana` | `grafana/grafana:12.2.0` | dashboards + alerts, provisioned from `../team6_monitoring` | 3000 |

Start order (health-check based): `db → mlflow → mlflow-bootstrap → model_service → webapp`; `db → airflow-init → airflow-*`.

## Files
* `.env.example` → copy to `.env` (never commit). Variables are documented inline.
* `run_project.sh` — installs data-script deps, prepares folders, generates 30 raw files, `docker compose down -v && up --build`.
* `mlflow/Dockerfile`, `nginx/default.conf`, `db_init/init-airflow-db.sql`.

## Useful commands
```bash
docker compose ps                                   # health of every service
docker compose logs -f airflow-scheduler            # follow a service
docker compose logs airflow-apiserver | grep "Password for user"   # Airflow admin password
docker compose exec model_service curl -s localhost:8000/model-info
docker compose exec model_service curl -s -X POST localhost:8000/reload-model
docker compose up -d --build <service>              # rebuild one service
docker compose down -v                              # full reset (deletes the database!)
```

## Troubleshooting
| Symptom | Likely cause / fix |
|---|---|
| `mlflow` never healthy / `database "mlflow" does not exist` | old Postgres volume from Defense 1 → `docker compose down -v` once (init script only runs on a fresh volume) |
| API logs `MLflow unavailable (attempt n/10)` | MLflow still starting; it retries and then falls back to the bundled model |
| Other containers get `403 Invalid Host header` from MLflow | a new hostname is used → add it to `--allowed-hosts` in the `mlflow` service |
| Airflow image build fails on `pip install` | the pinned versions must satisfy Airflow's constraints file (needs internet at build time) |
| Data Docs link 404 / nginx empty | no validation has run yet; wait for one ingestion run. On Linux make the folder writable: `chmod -R a+rwX ../team4_great_expectation/great_expectations` |
| Grafana panels empty | no data yet → run the traffic simulator (`../team3_data_training/scripts/simulate_traffic.py`) and wait for ingestion/prediction |
| Grafana alerts never reach Teams | `TEAMS_*_WEBHOOK_URL` unset → placeholder URL; set both in `.env` and `docker compose up -d grafana` |
| Training DAG always "skipped" | fewer than `min_new_files` new good files; trigger with `min_new_files = 0` |
| `PermissionError` writing `data/` or `mlflow-artifacts/` (Linux) | `chmod -R a+rwX ../team3_data_training/data mlflow-artifacts` |
