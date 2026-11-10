"""Runs every Grafana panel query and alert query against a REAL PostgreSQL database.

Grafana itself is not needed: the only Grafana-specific syntax used in the SQL is
``$__timeFilter(col)`` and the dashboard variable ``${num_feature}``, both expanded here.

Scenarios
  * healthy   - normal ingestion + predictions drawn from the training data  -> no alert may fire
  * bad data  - recent files all invalid / missing a column                  -> data-quality alerts fire
  * drift     - shifted features + constant predictions                      -> ML alerts fire

Run:  MONITORING_TEST_DB_URL=postgresql://user:pw@localhost:5432/test_db pytest team6_monitoring/tests
(skipped automatically when the variable is not set; CI provides a postgres service container)
"""
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GRAFANA = os.path.join(ROOT, "team6_monitoring", "grafana")
REFERENCE = os.path.join(ROOT, "team3_data_training", "healthcare-dataset-stroke-data.xls")

DB_URL = os.environ.get("MONITORING_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="MONITORING_TEST_DB_URL not set")

NUM = ["age", "avg_glucose_level", "bmi"]
CAT = ["gender", "ever_married", "work_type", "Residence_type", "smoking_status"]
NOW = datetime.now(timezone.utc)


# ----------------------------------------------------------------------------- helpers
def expand(sql: str, num_feature: str = "age") -> str:
    sql = re.sub(r"\$__timeFilter\(([^)]+)\)", r"\1 BETWEEN NOW() - INTERVAL '1 hour' AND NOW()", sql)
    return sql.replace("${num_feature}", num_feature)


def load_dashboard_queries():
    queries = []
    for name in ("data_quality.json", "drift_and_predictions.json"):
        with open(os.path.join(GRAFANA, "dashboards", name)) as fh:
            dash = json.load(fh)
        for panel in dash["panels"]:
            for tgt in panel["targets"]:
                queries.append(pytest.param(dash["uid"], panel["title"], tgt["rawSql"],
                                            id=f"{dash['uid']}:{panel['id']}"))
    return queries


def load_alert_queries():
    with open(os.path.join(GRAFANA, "provisioning", "alerting", "rules.yaml")) as fh:
        rules = yaml.safe_load(fh)
    out = {}
    for group in rules["groups"]:
        for r in group["rules"]:
            threshold = r["data"][2]["model"]["conditions"][0]["evaluator"]
            out[r["uid"]] = (r["data"][0]["model"]["rawSql"], threshold["type"], threshold["params"][0],
                             r["labels"]["team"])
    return out


def fires(value, op, threshold) -> bool:
    if value is None:
        return False  # no data / insufficient data -> rule state OK (noDataState: OK)
    return value > threshold if op == "gt" else value < threshold


@pytest.fixture(scope="module")
def conn():
    import psycopg2

    sys.path.insert(0, os.path.join(ROOT, "team5_service_web", "model_service"))
    from sqlalchemy import create_engine

    from app.models_orm import Base

    engine = create_engine(DB_URL.replace("postgresql://", "postgresql+psycopg2://"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)  # exactly the schema the API creates in production
    connection = psycopg2.connect(DB_URL)
    connection.autocommit = True
    yield connection
    connection.close()
    engine.dispose()


def run(conn, sql, num_feature="age"):
    with conn.cursor() as cur:
        cur.execute(expand(sql, num_feature))
        columns = [d[0] for d in cur.description]
        return columns, cur.fetchall()


def execute(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)


# ----------------------------------------------------------------------------- seeding
def reference() -> pd.DataFrame:
    df = pd.read_csv(REFERENCE).rename(columns={"Residence_type": "residence_type"})
    return df


def seed_baseline(conn, ref):
    execute(conn, "TRUNCATE training_stats RESTART IDENTITY")
    rows = []
    for col in NUM:
        s = ref[col]
        rows.append(("stroke_model_v1", True, col, "numerical", None, float(s.mean()), float(s.std()),
                     float(s.min()), float(s.max()), None, len(s)))
    for col in ["gender", "ever_married", "work_type", "residence_type", "smoking_status"]:
        for cat, prop in ref[col].astype(str).value_counts(normalize=True).items():
            rows.append(("stroke_model_v1", True, col, "categorical", cat, None, None, None, None, float(prop),
                         len(ref)))
    rows.append(("stroke_model_v1", True, "prediction", "prediction", "1", 0.2, 0.18, None, None, 0.15,
                 len(ref)))
    # a rejected candidate's stats must be ignored by every query (is_baseline = false)
    rows.append(("stroke_model_v2", False, "age", "numerical", None, 99.0, 1.0, 0.0, 100.0, None, 10))
    for r in rows:
        execute(conn, """INSERT INTO training_stats (model_version, is_baseline, feature_name, feature_type,
                         category, mean, std, min_value, max_value, proportion, n_rows)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", r)


def insert_prediction(conn, row, ts, pred, proba, version="stroke_model_v1"):
    execute(conn, """INSERT INTO predictions (prediction_time, source, model_version, gender, age, hypertension,
                     heart_disease, ever_married, work_type, residence_type, avg_glucose_level, bmi,
                     smoking_status, prediction, prediction_proba)
                     VALUES (%s,'scheduled',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (ts, version, row["gender"], float(row["age"]), int(row["hypertension"]), int(row["heart_disease"]),
             row["ever_married"], row["work_type"], row["residence_type"], float(row["avg_glucose_level"]),
             None if pd.isna(row["bmi"]) else float(row["bmi"]), row["smoking_status"], pred, proba))


def insert_ingestion(conn, ts, criticality, total, invalid, missing=False, errors=None):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO ingestion_stats (run_timestamp, source_filename, criticality, total_rows,
                       invalid_rows, invalid_percentage, missing_column)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (ts, f"f_{ts.timestamp()}.csv", criticality, total, invalid, 100.0 * invalid / total, missing))
        stat_id = cur.fetchone()[0]
        for error_type, count in (errors or {}).items():
            cur.execute("INSERT INTO ingestion_error_types (ingestion_stat_id, error_type, error_count) "
                        "VALUES (%s,%s,%s)", (stat_id, error_type, count))


def seed_healthy(conn):
    rnd = random.Random(1)
    ref = reference()
    seed_baseline(conn, ref)
    execute(conn, "TRUNCATE predictions, ingestion_error_types, ingestion_stats RESTART IDENTITY CASCADE")
    sample = ref.sample(n=500, random_state=3).reset_index(drop=True)
    for i, row in sample.iterrows():
        ts = NOW - timedelta(minutes=55) + timedelta(seconds=i * 6.4)
        positive = rnd.random() < 0.15
        proba = min(0.99, max(0.01, rnd.gauss(0.6 if positive else 0.12, 0.12)))
        insert_prediction(conn, row, ts, int(positive), proba, "stroke_model_v1" if i < 400 else "stroke_model_v3")
    kinds = ["none", "none", "low", "none", "medium"]
    errs = [None, None, {"null_required_field": 1}, None, {"value_out_of_range": 3, "invalid_categorical_value": 2}]
    for i in range(50):
        k = i % 5
        invalid = {"none": 0, "low": 1, "medium": 3}[kinds[k]]
        insert_ingestion(conn, NOW - timedelta(minutes=55 - i), kinds[k], 10, invalid, errors=errs[k])


def seed_bad_data(conn):
    execute(conn, "DELETE FROM ingestion_error_types WHERE ingestion_stat_id IN "
                  "(SELECT id FROM ingestion_stats WHERE run_timestamp > NOW() - INTERVAL '12 minutes')")
    execute(conn, "DELETE FROM ingestion_stats WHERE run_timestamp > NOW() - INTERVAL '12 minutes'")
    for i in range(3):  # all-errors files
        insert_ingestion(conn, NOW - timedelta(minutes=8 - i), "high", 10, 9,
                         errors={"null_required_field": 4, "wrong_type_value": 10, "statistical_outlier": 3})
    for i in range(3):  # schema errors
        insert_ingestion(conn, NOW - timedelta(minutes=5 - i), "high", 10, 0, missing=True)


def seed_drift(conn):
    ref = reference()
    execute(conn, "DELETE FROM predictions WHERE prediction_time > NOW() - INTERVAL '22 minutes'")
    sample = ref.sample(n=80, random_state=9).reset_index(drop=True)
    for i, row in sample.iterrows():
        row = row.copy()
        row["age"] = min(110.0, row["age"] + 35)
        row["avg_glucose_level"] = row["avg_glucose_level"] * 2.0
        row["smoking_status"] = "smokes"
        row["work_type"] = "Self-employed"
        insert_prediction(conn, row, NOW - timedelta(minutes=9) + timedelta(seconds=i * 6), 1, 0.5)  # constant output


# ----------------------------------------------------------------------------- tests
@pytest.mark.parametrize("uid,title,sql", load_dashboard_queries())
def test_every_panel_query_runs_and_returns_data(conn, uid, title, sql):
    seed_healthy(conn)
    features = NUM if "${num_feature}" in sql else ["age"]
    for feature in features:
        columns, rows = run(conn, sql, feature)
        assert rows, f"panel '{title}' returned no rows ({feature})"
        if "top_errors" not in sql and "error type" not in columns[0]:
            assert columns[0] == "time", f"first column of '{title}' must be the time column, got {columns[0]}"


def test_time_series_queries_with_metric_column_have_three_columns(conn):
    seed_healthy(conn)
    for _, _, sql in [p.values for p in load_dashboard_queries()]:
        columns, _ = run(conn, sql)
        if "metric" in columns:
            assert columns[:3] == ["time", "metric", "value"], columns


def test_drift_dashboard_ignores_non_baseline_stats(conn):
    """The rejected candidate (v2, mean age 99) must not be used as the baseline."""
    seed_healthy(conn)
    sql = next(p.values[2] for p in load_dashboard_queries() if p.values[1].startswith("Numerical feature drift"))
    _, rows = run(conn, sql, "age")
    baselines = {round(r[2], 1) for r in rows}
    assert baselines == {round(reference()["age"].mean(), 1)}


def test_healthy_system_fires_no_alert(conn):
    seed_healthy(conn)
    for uid, (sql, op, threshold, _team) in load_alert_queries().items():
        _, rows = run(conn, sql)
        value = rows[0][1] if rows else None
        assert not fires(value, op, threshold), f"{uid} fired on healthy data (value={value}, {op} {threshold})"


def test_bad_ingestion_fires_data_quality_alerts(conn):
    seed_healthy(conn)
    seed_bad_data(conn)
    alerts = load_alert_queries()
    for uid in ("dq-invalid-rate", "dq-schema-errors", "dq-high-criticality"):
        sql, op, threshold, team = alerts[uid]
        _, rows = run(conn, sql)
        value = rows[0][1]
        assert team == "data_quality"
        assert fires(value, op, threshold), f"{uid} did not fire (value={value})"


def test_drift_fires_ml_alerts(conn):
    seed_healthy(conn)
    seed_drift(conn)
    alerts = load_alert_queries()
    for uid in ("ml-numeric-drift", "ml-constant-predictions", "ml-positive-rate-shift"):
        sql, op, threshold, team = alerts[uid]
        _, rows = run(conn, sql)
        value = rows[0][1] if rows else None
        assert team == "ml"
        assert fires(value, op, threshold), f"{uid} did not fire (value={value})"


def test_drift_is_visible_on_the_dashboard_panels(conn):
    seed_healthy(conn)
    seed_drift(conn)
    panels = {p.values[1]: p.values[2] for p in load_dashboard_queries()}

    z_sql = next(s for t, s in panels.items() if t.startswith("Numerical drift score"))
    _, rows = run(conn, z_sql)
    assert max(max(v for v in r[1:] if v is not None) for r in rows[-2:]) >= 3

    tvd_sql = next(s for t, s in panels.items() if t.startswith("Categorical drift"))
    _, rows = run(conn, tvd_sql)
    assert max(r[2] for r in rows) >= 0.35

    spread_sql = next(s for t, s in panels.items() if t.startswith("Constant-prediction"))
    _, rows = run(conn, spread_sql)
    assert min(r[1] for r in rows) < 0.02

    range_sql = next(s for t, s in panels.items() if t.startswith("Share of serving values"))
    _, rows = run(conn, range_sql)
    assert max(r[2] for r in rows) >= 20  # glucose doubled -> many values above the training max


def test_model_version_panel_shows_both_versions(conn):
    seed_healthy(conn)
    sql = next(p.values[2] for p in load_dashboard_queries() if "per model version" in p.values[1])
    _, rows = run(conn, sql)
    assert {r[1] for r in rows} == {"stroke_model_v1", "stroke_model_v3"}


def test_error_categories_cover_all_five_dimensions(conn):
    seed_healthy(conn)
    seed_bad_data(conn)
    sql = next(p.values[2] for p in load_dashboard_queries() if p.values[1].startswith("Errors by validation category"))
    _, rows = run(conn, sql)
    found = {r[1] for r in rows}
    assert {"completeness", "validity", "consistency", "type", "schema (files)"} <= found
