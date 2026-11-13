"""Drift-baseline bookkeeping in PostgreSQL (dags/common/db_helpers.py).

Rules under test (Defense 2): training stats are stored per model version as NOT baseline;
only the promoted model's stats are the baseline; re-running a task must not duplicate rows.

Run:  MONITORING_TEST_DB_URL=postgresql://user:pw@localhost:5432/test_db pytest team6_monitoring/tests
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "team1_airflow", "dags"))

DB_URL = os.environ.get("MONITORING_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="MONITORING_TEST_DB_URL not set")

STATS = [
    {"feature_name": "age", "feature_type": "numerical", "mean": 43.0, "std": 22.0, "min_value": 0.1,
     "max_value": 82.0, "n_rows": 100},
    {"feature_name": "smoking_status", "feature_type": "categorical", "category": "smokes", "proportion": 0.15,
     "n_rows": 100},
    {"feature_name": "prediction", "feature_type": "prediction", "category": "1", "proportion": 0.2, "mean": 0.25,
     "std": 0.2, "n_rows": 100},
]


@pytest.fixture()
def hook():
    import psycopg2

    from common.simple_hook import SimpleHook

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS training_stats")
    conn.close()
    return SimpleHook(DB_URL)


def fetch(sql):
    import psycopg2

    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def test_table_is_created_on_demand_and_rows_are_not_baseline_yet(hook):
    from common import db_helpers

    assert db_helpers.insert_training_stats("stroke_model_v2", STATS, hook=hook) == 3
    assert fetch("SELECT DISTINCT is_baseline FROM training_stats") == [(False,)]


def test_rerunning_the_task_does_not_duplicate_rows(hook):
    from common import db_helpers

    db_helpers.insert_training_stats("stroke_model_v2", STATS, hook=hook)
    db_helpers.insert_training_stats("stroke_model_v2", STATS, hook=hook)
    assert fetch("SELECT COUNT(*) FROM training_stats")[0][0] == 3


def test_only_the_promoted_version_is_the_baseline(hook):
    from common import db_helpers

    for version in ("stroke_model_v1", "stroke_model_v2", "stroke_model_v3"):
        db_helpers.insert_training_stats(version, STATS, hook=hook)
    db_helpers.mark_baseline("stroke_model_v1", hook=hook)
    assert fetch("SELECT DISTINCT model_version FROM training_stats WHERE is_baseline") == [("stroke_model_v1",)]

    # v2 fails promotion (never marked) -> v1 stays the baseline; v3 is promoted later -> v3 takes over
    db_helpers.mark_baseline("stroke_model_v3", hook=hook)
    assert fetch("SELECT DISTINCT model_version FROM training_stats WHERE is_baseline") == [("stroke_model_v3",)]
    assert fetch("SELECT COUNT(*) FROM training_stats WHERE is_baseline")[0][0] == 3


def test_schema_matches_the_orm_model_used_by_the_api(hook):
    """The DAG creates the table with raw SQL, the API with SQLAlchemy: columns must agree."""
    from common import db_helpers

    db_helpers.ensure_training_stats_table(hook=hook)
    sys.path.insert(0, os.path.join(ROOT, "team5_service_web", "model_service"))
    from app.models_orm import TrainingStat

    sql_columns = {r[0] for r in fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'training_stats'")}
    assert sql_columns == {c.name for c in TrainingStat.__table__.columns}
