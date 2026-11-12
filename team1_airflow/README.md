# team1_airflow — DAGs and Airflow image

* `Dockerfile` / `requirements.txt` — custom image on `apache/airflow:3.1.0-python3.12`; packages installed under Airflow's
  constraints file. Versions of pandas / numpy / scikit-learn / joblib are identical to the model_service image.
* `dags/ingestion_dag.py` — every minute: read → validate (Great Expectations) → save stats → alert → split good/bad.
* `dags/prediction_dag.py` — every 2 minutes: new `good_data` files → model API.
* `dags/training_dag.py` — every 10 minutes: load_data → train_model → save_training_stats → evaluate_candidate →
  promote_to_champion → notify_api_reload + archive_data. Trigger-time params: `min_new_files`, `primary_metric`,
  `inference_time_threshold_ms`, `min_improvement`.
* `dags/common/` (ignored by the DAG parser via `.airflowignore`)
  `gx_helpers` (validation + Data Docs URL) · `db_helpers` (ingestion + training stats, PostgresHook) ·
  `alert_helpers` (Teams Adaptive Cards, two channels) · `training_helpers` (pure data/model logic, unit tested) ·
  `mlflow_helpers` (registry client) · `bootstrap_registry` (first champion) · `simple_hook` (psycopg2 stand-in).
