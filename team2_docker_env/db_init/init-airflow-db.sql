-- The default POSTGRES_DB (dsp_app) is created automatically by the postgres image.
-- The same instance also hosts two extra databases:
--   airflow : Airflow metadata
--   mlflow  : MLflow backend store (experiments, runs, model registry)
-- NOTE: init scripts only run when the pg_data volume is created. If you upgrade an existing
-- Defense 1 volume, run `docker compose down -v` once (run_project.sh already does this).
CREATE DATABASE airflow;
CREATE DATABASE mlflow;
