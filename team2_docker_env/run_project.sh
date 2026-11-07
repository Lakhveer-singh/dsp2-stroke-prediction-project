#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

INSTALLER=(python3 -m pip)
if command -v uv >/dev/null 2>&1; then
  INSTALLER=(uv pip)
fi

echo "=== DSP-share project setup ==="
echo "Using installer: ${INSTALLER[*]}"

test -f .env || {
  cp .env.example .env
  echo "Created .env from .env.example"
}

echo ""
echo "1) Verify .env contents"
echo "   - POSTGRES_USER"
echo "   - POSTGRES_PASSWORD"
echo "   - POSTGRES_DB"
echo "   - DATABASE_URL"
echo "   - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
echo "   - AIRFLOW__CORE__FERNET_KEY"
echo "   - AIRFLOW__API_AUTH__JWT_SECRET"
echo "   - _AIRFLOW_WWW_USER_USERNAME"
echo "   - _AIRFLOW_WWW_USER_PASSWORD"
echo "   - MODEL_PATH"
echo "   - API_BASE_URL"
echo "   - TEAMS_WEBHOOK_URL"
echo ""

echo "2) Install Python requirements"
cd ../team3_data_training
"${INSTALLER[@]}" install -r scripts/requirements.txt
"${INSTALLER[@]}" install -r model_training/requirements.txt

echo "3) Generate ingestion data"
if [[ -f healthcare-dataset-stroke-data.xls ]]; then
  echo "Generating raw data files from healthcare-dataset-stroke-data.xls"
  mkdir -p data/raw_data
  python3 scripts/split_dataset.py --input healthcare-dataset-stroke-data.xls --output-dir /tmp/clean_split --num-files 30
  for f in /tmp/clean_split/*.csv; do
    python3 scripts/inject_errors.py --input "$f" --output "data/raw_data/$(basename "$f")"
  done
else
  echo "No clean dataset file found in team3_data_training/. Skipping data generation."
fi

echo "4) Start Docker services"
cd "$PROJECT_ROOT"
docker compose down --volumes --remove-orphans || true
docker compose up --build
