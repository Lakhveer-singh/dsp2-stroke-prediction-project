# DSP Stroke Prediction

End-to-end data pipeline for stroke-risk prediction, built for the EPITA Data
Science in Production course (Defense 1 scope).

## Architecture

| Folder | Owner | Responsibility |
|---|---|---|
| `team1_airflow` | Airflow DAGs | Ingestion + prediction DAGs (validation, splitting, alerting, batching) |
| `team2_docker_env` | Docker/env | `docker-compose.yml`, `.env` management, one-command project startup |
| `team3_data_training` | Data & training | Dataset split, error injection, model training notebook, shared tests |
| `team4_great_expectation` | Data validation | Great Expectations Suite / Validation Definition / Checkpoint |
| `team5_service_web` | Service & web | FastAPI model service + Streamlit webapp, CI |

## Prerequisites

- Docker Desktop (with Compose v2 — `docker compose`, not `docker-compose`)
- Python 3.12 (for local script/test runs outside Docker)

## Setup & run

1. Copy the environment template and fill in real secrets:
   ```bash
   cd team2_docker_env
   cp .env.example .env
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```
   Paste the generated values into `AIRFLOW__CORE__FERNET_KEY` and
   `AIRFLOW__API_AUTH__JWT_SECRET` in `.env`.

2. Start everything:
   ```bash
   bash run_project.sh
   ```
   This generates the 30 demo ingestion files, then runs `docker compose up --build`.

3. Once containers are healthy:
   - Streamlit webapp: http://localhost:8501
   - Airflow UI: http://localhost:8080
     (password: `docker compose logs airflow-apiserver | grep "Password for user"`)

See `team2_docker_env/README.md` for full details, troubleshooting, and known limitations.
