# DSP — Stroke Prediction (Defense 1)

MLOps pipeline for predicting stroke risk from patient data ([healthcare-dataset-stroke-data.xls](../team3_data_training/healthcare-dataset-stroke-data.xls), Kaggle stroke dataset). Built for the Data Science in Production course — this repo covers **Defense 1 scope only**:

- Streamlit webapp (single/batch predictions + past predictions)
- FastAPI model service (model loaded from a local file, no MLflow yet)
- PostgreSQL (predictions + ingestion stats)
- Airflow 3.x: ingestion DAG (Great Expectations validation, stats, Teams alerts, good/bad routing) and prediction DAG (scheduled batch predictions)
- Data splitting and error-injection scripts
- GitHub Actions CI (flake8 + pytest, as separate jobs)

Out of scope (Defense 2): MLflow model registry / `/reload-model`, nginx-served Data Docs links, CD/release pipeline, drift-monitoring dashboard.

## Folder structure

This repo (`team2_docker_env`) only holds orchestration — the app code lives in sibling team repos and is wired in via relative paths in `docker-compose.yml` (no symlinks, no copies):

```
team2_docker_env/                        # this repo — orchestration only
  db_init/                                # Postgres init script (creates the airflow database)
  docker-compose.yml                      # builds/mounts the sibling repos below by relative path
  .env.example

../team1_airflow/dags/                   # Airflow DAGs (ingestion_dag.py, prediction_dag.py) + shared helpers
../team3_data_training/
  model_training/                         # Model exploration + training notebook, trained artifact
  scripts/                                # Data splitting / error-injection CLIs
  tests/                                  # Repo-level tests (splitting, criticality, stats)
  data/                                   # raw_data (unprocessed) / good_data / bad_data / archived_data
  healthcare-dataset-stroke-data.xls
../team4_great_expectation/great_expectations/   # GX Core v1.x project (expectation suite, checkpoint)
../team5_service_web/
  model_service/                          # FastAPI app
  webapp/                                 # Streamlit app
  .github/workflows/                      # CI pipeline (flake8 + pytest, separate jobs)
```

## Prerequisites

- Docker and Docker Compose (`docker compose version`)
- Python 3.12 (only needed to run the data scripts / notebook locally, not required to run the app itself)

## Setup

1. Fill in `.env` (auto-created from `.env.example` on first run if missing):
   - Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   - JWT secret: `python -c "import secrets; print(secrets.token_hex(32))"`
   - `TEAMS_WEBHOOK_URL` is optional — ingestion alerts are silently skipped if unset

2. Make sure Docker Desktop is running, then from an environment with Python 3.12 + pip (e.g. `conda activate dsp`):
   ```bash
   bash run_project.sh
   ```
   This installs the data/training Python deps, generates demo ingestion data, and brings up the full stack (`docker compose up --build`). It resets the Postgres volume on every run for a clean demo state, and runs in the foreground — leave the terminal open and use your browser for the demo. First startup also runs `airflow-init` once (DB migration + admin user creation).

To retrain the model instead of using the committed one (`../team5_service_web/model_service/app/artifacts/model_pipeline.pkl`): run `train_model.ipynb` in `../team3_data_training/model_training/`, then copy the resulting `artifacts/model_pipeline.pkl` over the committed one.

## Accessing the services

| Service | URL | Notes |
|---|---|---|
| Streamlit webapp | http://localhost:8501 | Prediction + Past Predictions pages |
| Airflow UI | http://localhost:8080 | Login `admin` / auto-generated password — Airflow 3's Simple Auth Manager ignores `.env` and logs a random password once on first boot: `docker compose logs airflow-apiserver \| grep "Password for user"` |
| Model service API | not exposed on the host | internal only, reached via `http://model_service:8000` on the Docker network (Streamlit/Airflow call it directly) |

The Postgres Connection (`dsp_app_db`) and the Teams webhook Variable (`teams_webhook_url`) used by the DAGs are provisioned automatically via environment variables (`AIRFLOW_CONN_DSP_APP_DB`, `AIRFLOW_VAR_TEAMS_WEBHOOK_URL`) — no manual setup needed in the Airflow UI.

## Generating demo data

`run_project.sh` already generates 30 error-injected demo files into `../team3_data_training/data/raw_data/` on every run — the ingestion DAG (`*/1 * * * *`) picks a random one each minute; the prediction DAG (`*/2 * * * *`) picks up anything that lands in `data/good_data/`.

To generate custom data instead (e.g. for a live defense demo), from `../team3_data_training/`:
```bash
python scripts/split_dataset.py --input healthcare-dataset-stroke-data.xls --output-dir /tmp/clean_split --num-files 30
for f in /tmp/clean_split/*.csv; do
  python scripts/inject_errors.py --input "$f" --output "data/raw_data/$(basename "$f")"
done
```
Error probabilities are configurable per type — see `python scripts/inject_errors.py --help`.

Before a live defense, empty `data/good_data/` and `data/bad_data/`, and prepare 5 demo files outside `raw_data/` (1 all-errors, 3 clean, 1 mixed) to copy in live.

## Running tests locally

Each part is linted/tested from its own repo:

```bash
# team5_service_web (webapp + model_service)
cd ../team5_service_web
pip install -r requirements-dev.txt -r webapp/requirements.txt -r model_service/requirements.txt
flake8 .
cd model_service && PYTHONPATH=. pytest tests/ -q
cd ../../team2_docker_env

# team3_data_training (scripts + model_training + repo-level tests)
cd ../team3_data_training
pip install -r scripts/requirements.txt -r model_training/requirements.txt -r tests/requirements-test.txt
PYTHONPATH=../team1_airflow pytest tests/ -q
cd ../team2_docker_env
```

Note: `tests/test_criticality.py` and `tests/test_stats_computation.py` import the validation helper directly from `team1_airflow`'s `dags.common.gx_helpers` (the same module the ingestion DAG uses at runtime), so `PYTHONPATH` must include `../team1_airflow` for these tests to collect. That module now runs a real GX checkpoint, so `tests/requirements-test.txt` installs `great_expectations` too, and `tests/conftest.py` automatically points `GX_CONTEXT_ROOT_DIR` at `../team4_great_expectation/great_expectations/gx` so this works out of the box, both locally and in CI.

## Known limitations

- With ingestion files fixed at exactly 10 rows (per spec), "low" criticality (0–10% invalid) is effectively unreachable — one invalid row out of ten is already 10%, which the spec's own thresholds classify as "medium". This is a consequence of the two spec-mandated constraints together, not a bug.
- All validation now runs through the real GX `stroke_checkpoint` (Expectation Suite → Validation Definition → Checkpoint → Data Docs) — `gx_helpers.py` contains no hardcoded pandas rules. The `wrong_type_value` category comes from `expect_column_values_to_be_of_type`, which checks the pandas column's dtype rather than individual values: a single stray non-numeric value upcasts the whole column to `object` dtype, so GX (correctly) flags every row in that column as suspect, not just the offending one.
- The "additional error type" beyond the 5 required categories is a statistical outlier check (`avg_glucose_level` far outside any plausible reading, e.g. a sensor glitch), rather than cross-field inconsistency — GX Core has no built-in expectation for cross-column logic (e.g. `work_type == "children"` with `age > 18`) without writing a custom Expectation class, so we picked a check GX supports natively instead.
