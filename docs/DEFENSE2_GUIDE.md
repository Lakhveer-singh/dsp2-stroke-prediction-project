# Defense 2 guide — what was added, why, and how to explain it

Read this once from top to bottom. Every team member must be able to explain the parts listed for them in
`TEAM_TASKS.md`; everybody must know Airflow and Docker (section 7).

## 1. What changed compared with Defense 1

| Area | Defense 1 | Defense 2 | Main files |
|---|---|---|---|
| Model serving | `joblib.load` of a file in the image | loads `models:/stroke_model@champion` from **MLflow**; thread-safe holder; fallback to the file | `model_service/app/model_registry.py`, `main.py` |
| API | `/health /predict /past-predictions` | + **`POST /reload-model`**, `GET /model-info` | `routers/reload_model.py`, `schemas.py` |
| Database | `predictions`, `ingestion_stats`, `ingestion_error_types` | + **`training_stats`** (drift baseline per model version) | `models_orm.py`, `db_helpers.py` |
| Airflow | 2 DAGs, extra pip packages installed at every container start | + **`training_dag`**; custom **image** (packages baked in, installed under Airflow's constraints) | `training_dag.py`, `common/training_helpers.py`, `common/mlflow_helpers.py`, `team1_airflow/Dockerfile` |
| Alerts | one Teams webhook, MessageCard | **two channels**, Adaptive Cards, link to the **nginx-served Data Docs report** | `common/alert_helpers.py`, `common/gx_helpers.py` |
| Docker | db, api, webapp, airflow x4 | + **mlflow**, **mlflow-bootstrap**, **nginx**, **grafana** | `docker-compose.yml` |
| Monitoring | – | 2 Grafana dashboards + 6 alert rules + routing, all provisioned as code | `team6_monitoring/` |
| CI/CD | CI only | CI extended; **CD**: GitHub Release with semantic version | `.github/` |
| Model | notebook config | shared `training_helpers.build_pipeline` (slightly better regularised forest) | `common/training_helpers.py` |

Defense-1 code paths (`ingestion_dag`, `prediction_dag`, webapp pages, `/predict`) were kept; only `send_alerts`
in the ingestion DAG changed (new alert format + link) and the webapp shows the model version.

## 2. The model lifecycle in one picture

```
 reference dataset ──fixed 20 % hold-out──────────────► TEST SET (never trained on, same rows every time)
        │
        └─80 %──► train split ─┐
 good_data files ─(labels looked up, test-overlap removed)─┴► TRAINING SET ──► candidate model ──► MLflow registry (version N)
                                                                                 │
                         champion (version M) ◄── compared on the SAME test set ─┘
                                 │
        candidate ≥ champion AND fast enough?  ── yes ─► alias "champion" → N ─► training_stats(N) = baseline
                                 │                                    └► POST /reload-model ─► API serves N, archive files
                                 └─ no ─► nothing changes, alert to "ML Alerts", reason logged in MLflow
```

**Registry vs alias.** Every trained model is a *version* in the MLflow Model Registry (1, 2, 3…). The alias
`champion` is a movable pointer to one version. "Promotion" = moving the pointer. The API always asks for
`models:/stroke_model@champion`, so it never needs to know version numbers. `/reload-model` makes it re-resolve
the pointer and swap the model in memory.

**Why a lock (`ModelHolder`).** `/predict` reads *(model, version)* together; `/reload-model` replaces both together.
Without the lock a prediction could be computed by the old model but labelled with the new version.
If loading the new model fails, nothing is swapped and the old model keeps serving.

**Bootstrap.** `mlflow-bootstrap` (one-shot container) trains version 1 on the reference data, aliases it `champion`
and stores its statistics as the first drift baseline, so the API and the drift dashboard work from the first second.
It is idempotent (does nothing if a champion exists).

## 3. Design choices you will be asked about

* **Primary metric = F1 (configurable).** Only ~5 % of patients have a stroke, so accuracy is meaningless (a model that
  always says "no stroke" scores 95 %). The Defense 1 notebook model had F1 = 0 on the hold-out (it never predicted a stroke),
  therefore the shared pipeline uses `balanced_subsample` + `min_samples_leaf=10` (F1 ≈ 0.34, ROC-AUC ≈ 0.82).
* **Fair comparison.** Champion and candidate are scored by the DAG *on the same fixed hold-out*; the champion is
  re-scored from the registry, not read from a stored number. Good rows identical to a test row are removed from training.
* **Where do labels come from?** Ingested files carry no label (course rule). We *simulate delayed ground truth* by looking
  the rows up in the labelled dataset. Honest limitation: in a real system labels would arrive from a business process.
* **Inference time.** Mean latency of *one* single-row `predict` + `predict_proba` (what the API does for a webapp request),
  after a warm-up call. Limit 200 ms (≈ 20 ms measured).
* **Drift baseline.** `training_stats` stores, per model version: mean/std/min/max of numerical features, category
  proportions, and the model's own predicted-positive rate. Stats are saved *before* evaluation but flagged
  `is_baseline = false`; `promote_to_champion` flips the flag so only the champion's stats are the reference.
* **Drift measures.** Numerical: z-score of the 5-minute mean = |serving mean − training mean| / (training std / √n); ≥ 3
  is far beyond sampling noise. Categorical: total variation distance (½ Σ |p_serving − p_training|). Plus out-of-range share,
  positive-prediction rate, probability spread (constant-prediction detector), rate per model version.
* **Skip logic.** `load_data` raises `AirflowSkipException` when too few new files arrived; every downstream task is skipped.
  `promote_to_champion` skips itself when rejected, which skips `notify_api_reload` and `archive_data` — a failed
  candidate never touches the API or the data.
* **Archive safety.** Only files the prediction DAG has already scored are archived; others stay for the next run.
* **Single DB instance, three databases:** `dsp_app` (data), `airflow` (metadata), `mlflow` (registry).
* **Custom Airflow image.** Defense 1 pip-installed packages in every container at start-up. Now they are baked in at build,
  under Airflow's official constraints file (so nothing in the base image is upgraded and conflicts fail at *build* time).
* **API and Airflow use the same scikit-learn/pandas/numpy versions** because a pickled model must be loaded with the
  library version that wrote it.
* **MLflow serialization** = `cloudpickle` (MLflow 3's default `skops` needs an extra package and trusted-type lists).
* **MLflow `--allowed-hosts`:** MLflow rejects unknown `Host` headers (DNS-rebinding protection). Other containers call
  `http://mlflow:5000`, so that name is whitelisted.
* **Grafana as code.** Datasource, dashboards, contact points, notification policy and alert rules are files under
  `team6_monitoring/grafana/provisioning` — reproducible with `docker compose up`, reviewable in Git. The dashboards and
  rules are generated by `tools/build_monitoring.py` so that tests can run the *same SQL* against PostgreSQL.
* **Alert routing.** Rules carry a label `team=data_quality|ml`; the notification policy routes by that label to the
  matching Teams contact point. Airflow sends its own alerts straight to the same two channels.

## 4. Monitoring: what each panel/alert means

Data quality dashboard: invalid % per file (criticality colours) · errors by category (completeness = null required field,
validity = out-of-range / impossible / outlier, consistency = unknown category, type = wrong type, schema = missing column) ·
criticality over time · rejected-row share · most frequent error types · schema errors.
Alerts: >50 % rows rejected in 10 min · ≥2 missing-column files in 10 min · ≥3 high-criticality ingestions in 10 min.

Drift dashboard: serving mean vs baseline (feature picker) · z-score · categorical distance · out-of-range share ·
positive rate vs baseline · probability bands · spread (constant predictions) · positive rate per model version.
Alerts: z-score > 3 (≥15 predictions/15 min) · prediction-probability std < 0.01 (≥20 predictions/10 min) ·
positive-rate shift > 25 points (15 min).

## 5. Likely questions (short answers)

1. **Why alias instead of stages?** Stages are deprecated in MLflow 2/3; aliases are the supported mechanism.
2. **What if MLflow is down when the API starts?** It retries (10 × 3 s), then serves the bundled fallback model.
3. **What if `/reload-model` fails?** HTTP 502/404; the previous model keeps serving; the DAG task retries 3 times.
4. **How does the API know a new model is ready?** The DAG calls `/reload-model` after moving the alias; the DAG checks the
   returned version label equals the promoted one.
5. **How do you avoid leakage?** Fixed hold-out; good rows matching hold-out rows are dropped from training.
6. **Why is the training set bigger than the new data?** Reference train split + labelled new rows (the new rows are samples of
   the same population, so in this simulation many duplicate reference rows; acceptable and documented).
7. **What triggers retraining?** Schedule (10 min) + enough new files. A drift-triggered retraining was not implemented.
8. **How do you prevent a bad model from going live?** Promotion rule + failed-promotion alert; the failed version stays in the
   registry but is never aliased.
9. **Why separate `is_baseline` flag?** So a rejected candidate's statistics never become the drift reference.
10. **Why `date_bin`/5-minute buckets?** Smooths the per-file noise; each dashboard point aggregates several files.
11. **Why z-score with √n?** The mean of n samples has std σ/√n; dividing makes the score independent of the bucket size.
12. **How are the dashboards loaded?** Grafana file provisioning mounts `team6_monitoring/grafana/*` read-only.
13. **How is the Data Docs link built?** GX returns a `file://…/local_site/<page>` URL; we replace the prefix with
    `DATA_DOCS_PUBLIC_URL` (nginx), preserving the page path of that exact validation run.
14. **Why two webhooks?** Different audiences: data operations vs ML engineers.
15. **CD?** On `push` to `main` the workflow computes the next semantic version from commit messages and creates a GitHub
    Release with notes — the "delivery" of a locally-run project.
16. **What would you change for production?** Real label feedback, model signature/schema enforcement, authentication on
    `/reload-model`, object storage for artifacts, drift-triggered retraining, proper secrets management.

## 6. Verification status (be honest on slide 1!)

Verified during development with real components (not mocks): PostgreSQL 16, MLflow 3.17.2 server (PostgreSQL backend,
artifact proxy, host allow-list), Airflow 3.1.0 (`dags reserialize`, `dag.test()` of ingestion/prediction/training),
Great Expectations 1.18.2, the FastAPI app, every Grafana SQL query on seeded and real pipeline data, the Teams payloads
(captured by a local receiver), the Data Docs links (HTTP 200), the semantic-version script, about 120 unit/integration tests.

**NOT verified in the environment where the code was written (no Docker available there)** — check these first on your
machine and list anything that fails on slide 1:
`docker compose up --build` end to end (image builds, health checks, start-up order) · Grafana provisioning and alert
evaluation inside a running Grafana 12.2 (dashboards rendering, contact points, routing, rules evaluating) · nginx serving
the Data Docs · delivery to real Teams channels · the GitHub Actions workflows on GitHub · permissions of bind-mounted
folders on Linux hosts.

## 7. Airflow & Docker questions every member must handle
Airflow 3: DAG / task / TaskFlow `@task`, scheduler vs api-server vs dag-processor, XCom (small JSON between tasks),
Variables and Connections (here from env vars `AIRFLOW_VAR_*`, `AIRFLOW_CONN_*`), `catchup=False`, `max_active_runs`,
skip vs fail, retries, DAG `params`, how the DAG folder is mounted. Docker: image vs container, `build`, volumes and bind
mounts, networks and service names, `depends_on` + `service_healthy`, health checks, `restart`, `.env`,
`docker compose up --build / down -v / logs -f / exec`.
