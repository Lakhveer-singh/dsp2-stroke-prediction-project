#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

INSTALLER=(python3 -m pip)
if command -v uv >/dev/null 2>&1; then
  INSTALLER=(uv pip)
fi

echo "=== DSP project setup (Defense 1 + 2) ==="
echo "Using installer: ${INSTALLER[*]}"

test -f .env || {
  cp .env.example .env
  echo "Created .env from .env.example"
  echo "  -> edit it now: Fernet key, JWT secret, SECRET_KEY and (optionally) the two Teams webhooks"
}

echo ""
echo "1) Verify .env contents"
echo "   - POSTGRES_* / DATABASE_URL / AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
echo "   - AIRFLOW__CORE__FERNET_KEY, AIRFLOW__API_AUTH__JWT_SECRET, AIRFLOW__WEBSERVER__SECRET_KEY"
echo "   - TEAMS_DQ_WEBHOOK_URL (Data Quality Alerts), TEAMS_ML_WEBHOOK_URL (ML Alerts)  [optional]"
echo ""

echo "2) Install Python requirements for the data scripts"
cd ../team3_data_training
"${INSTALLER[@]}" install -r scripts/requirements.txt

echo "3) Prepare data folders + generate ingestion data"
mkdir -p data/raw_data data/good_data data/bad_data data/archived_data
# Docker bind mounts: make sure the folders Airflow / nginx write to exist and are writable
# (otherwise Docker creates them root-owned on Linux hosts).
mkdir -p ../team4_great_expectation/great_expectations/gx/uncommitted/data_docs/local_site
chmod -R a+rwX data ../team4_great_expectation/great_expectations 2>/dev/null || true
mkdir -p "$PROJECT_ROOT/mlflow-artifacts"
chmod -R a+rwX "$PROJECT_ROOT/mlflow-artifacts" 2>/dev/null || true

if [[ -f healthcare-dataset-stroke-data.xls ]]; then
  echo "Generating raw data files from healthcare-dataset-stroke-data.xls"
  rm -f data/raw_data/*.csv data/good_data/*.csv data/bad_data/*.csv data/archived_data/*.csv
  rm -rf /tmp/clean_split
  python3 scripts/split_dataset.py --input healthcare-dataset-stroke-data.xls --output-dir /tmp/clean_split --num-files 30
  for f in /tmp/clean_split/*.csv; do
    python3 scripts/inject_errors.py --input "$f" --output "data/raw_data/$(basename "$f")"
  done
else
  echo "No clean dataset file found in team3_data_training/. Skipping data generation."
fi

echo "4) Start Docker services (first build takes several minutes: Airflow + MLflow images)"
cd "$PROJECT_ROOT"
docker compose down --volumes --remove-orphans || true
rm -rf ../team4_great_expectation/great_expectations/gx/uncommitted/validations \
       ../team4_great_expectation/great_expectations/gx/uncommitted/data_docs 2>/dev/null || true
mkdir -p ../team4_great_expectation/great_expectations/gx/uncommitted/data_docs/local_site
chmod -R a+rwX ../team4_great_expectation/great_expectations 2>/dev/null || true
docker compose up --build
