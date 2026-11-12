# Demo script (≈ 10 minutes) and pre-defense checklist

Rules recap (from the course): demo from `main`, on ONE computer, only demoed features count, do not demo broken
features (list them on slide 1), time is strict, Data Docs must render in a browser.

## A. Days before the defense — make the dashboards meaningful
1. `cd team2_docker_env && docker compose up -d --build` (do NOT use `run_project.sh` — it wipes volumes).
2. Start the traffic simulator (genuine pipeline data, one file per minute):
   `cd ../team3_data_training && python scripts/simulate_traffic.py --input healthcare-dataset-stroke-data.xls --raw-dir data/raw_data --interval 60 --duration-min 1440`
   Run it for as long as you can (it moves through normal → bad-data burst → normal → drift).
3. Let the training DAG run on schedule (every 10 min) — you should see several MLflow versions and at least one
   promotion and one rejection. Check Grafana → both dashboards have curves, `positive rate per model version` shows ≥ 2 lines.
4. Create the 2 Teams channels and set both webhooks in `.env`; verify a message arrives in each.
5. Keep the same environment on a **second computer** (`git clone`, same `.env`, same steps).

## B. The morning of the defense (join 15 minutes early)
- [ ] On `main`: `git status` clean, `git branch -a` shows only `main` and `develop`
- [ ] `docker compose ps` → everything `healthy`/`running` (no restart loops)
- [ ] Empty the folders: `rm -f team3_data_training/data/{raw_data,good_data,bad_data}/*.csv` (keep `archived_data`)
- [ ] **Stop the simulator** and make sure `raw_data` is empty
- [ ] `python scripts/generate_demo_data.py --input healthcare-dataset-stroke-data.xls --output-dir ~/demo_files --n-drift 8`
      → 5 demo files: `demo_01..03_clean`, `demo_04_mixed`, `demo_05_all_errors` (+ `demo_06_missing_column`, `drift_*`)
- [ ] Browser tabs ready: webapp :8501 · Airflow :8080 · MLflow :5000 · Grafana :3000 (both dashboards) · Data Docs :8081 · GitHub Releases page · Teams channels
- [ ] Grafana time range `Last 1 hour`/`6 hours`, auto-refresh on; dashboards show data (empty dashboards = not done)
- [ ] Slides PDF + repo link submitted in Teams (missing = −2)

## C. Timeline (≈ 10 min)

| min | What you do | What you say / show |
|---|---|---|
| 0:00 | 2 slides (≈ 1 min) | honest list of what does not work; who did what |
| 1:00 | `docker compose ps` | all services healthy; one compose file; show webapp **Prediction** page → single prediction, result table shows `model_version` |
| 1:45 | **Ingestion, all errors**: `cp ~/demo_files/demo_05_all_errors.csv team3_data_training/data/raw_data/` (or trigger `ingestion_dag` in Airflow) | file lands in `bad_data`; Teams **Data Quality Alerts** message → click **Open Data Docs report** → rendered report in the browser (nginx :8081) |
| 3:00 | **Clean + mixed**: copy `demo_01/02/03_clean.csv` and `demo_04_mixed.csv` | clean → `good_data`; mixed → split (7 good / 3 bad); webapp **Past predictions** (source `scheduled`) shows the new predictions |
| 4:00 | **Grafana – data quality**: walk through the 6 panels; open the alert rule list (3 DQ rules, label `team=data_quality`) | colours = criticality; 5 error categories; contact point → Data Quality Alerts channel |
| 5:00 | **MLflow**: experiment `stroke_prediction` (runs + metrics), Models → `stroke_model`, alias `champion` | explain candidate/champion/alias |
| 5:45 | **Training DAG**: Airflow → `training_dag` → *Trigger with config*: `min_new_files = 0`, `min_improvement = -1` → watch the 7 tasks | explain each task; after success: MLflow alias moved, `notify_api_reload` green, `archived_data` has the files; webapp prediction now shows the **new model_version** (no restart) |
| 7:15 | **Rejected candidate**: trigger again with `inference_time_threshold_ms = 0.001` | `promote_to_champion`, `notify_api_reload`, `archive_data` **skipped**; Teams **ML Alerts** message with the reason; MLflow run tags `promotion_decision=rejected` |
| 8:00 | **Grafana – drift**: show the drift dashboard (history); copy `drift_01..08.csv` to `raw_data` beforehand or show the history from the simulator's drift phase | z-score turns red, categorical distance, positive rate per model version; ML alert rules |
| 9:00 | **CD**: GitHub → Releases (version tag + notes); `.github/workflows` | semantic versioning on `develop → main` |
| 9:30 | stop | Q&A |

Tips
* Use *Trigger DAG* in the Airflow UI instead of waiting for the schedule; the ingestion DAG picks a random file from
  `raw_data`, so put **one file at a time** there.
* After a training run the same files are "used" (`training_seen_good_data_files`), so for a *second* training demo either
  trigger with `min_new_files = 0` or add new files (unique names!).
* `archive_data` only moves files the prediction DAG has already scored (it runs every 2 min): wait for the predictions of the
  demo files to appear in *Past predictions* before triggering the training DAG, otherwise `archived_data` stays empty.
* A promotion is *not guaranteed* (F1 on ~50 positives is noisy). That is why both runs above force the outcome with params.
* If a Teams message does not arrive, show the Airflow task log line `Teams alert failed` — do not claim it worked.
* Do not demo anything you listed on slide 1.

## D. Reset between rehearsals
`cd team2_docker_env && docker compose down -v && bash run_project.sh`
