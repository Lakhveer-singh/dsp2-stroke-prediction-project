try:
    from airflow.providers.postgres.hooks.postgres import PostgresHook
except ImportError:  # unit tests / bootstrap run without Airflow and pass their own hook
    PostgresHook = None

CONN_ID = "dsp_app_db"


def insert_ingestion_stat(
    source_filename: str,
    criticality: str,
    total_rows: int,
    invalid_rows: int,
    invalid_percentage: float,
    missing_column: bool,
) -> int:
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    row = hook.get_first(
        """
        INSERT INTO ingestion_stats
            (source_filename, criticality, total_rows, invalid_rows, invalid_percentage, missing_column)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        parameters=(source_filename, criticality, total_rows, invalid_rows, invalid_percentage, missing_column),
    )
    return row[0]


def insert_ingestion_error_types(ingestion_stat_id: int, error_counts: dict) -> None:
    if not error_counts:
        return
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    rows = [(ingestion_stat_id, error_type, count) for error_type, count in error_counts.items() if count > 0]
    if rows:
        hook.insert_rows(
            table="ingestion_error_types",
            rows=rows,
            target_fields=["ingestion_stat_id", "error_type", "error_count"],
        )


# --------------------------------------------------------------------------- Defense 2
# training_stats: feature distribution of each trained model (drift baseline for Grafana)

TRAINING_STATS_FIELDS = [
    "model_version", "is_baseline", "feature_name", "feature_type", "category",
    "mean", "std", "min_value", "max_value", "proportion", "n_rows",
]

CREATE_TRAINING_STATS_SQL = """
CREATE TABLE IF NOT EXISTS training_stats (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version VARCHAR(50) NOT NULL,
    is_baseline BOOLEAN NOT NULL DEFAULT FALSE,
    feature_name VARCHAR(50) NOT NULL,
    feature_type VARCHAR(20) NOT NULL,
    category VARCHAR(50),
    mean DOUBLE PRECISION,
    std DOUBLE PRECISION,
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    proportion DOUBLE PRECISION,
    n_rows INTEGER
);
CREATE INDEX IF NOT EXISTS ix_training_stats_model_version ON training_stats (model_version);
CREATE INDEX IF NOT EXISTS ix_training_stats_is_baseline ON training_stats (is_baseline);
"""


def ensure_training_stats_table(hook=None) -> None:
    """The API also creates this table at startup; this keeps the DAG independent of start order."""
    hook = hook or PostgresHook(postgres_conn_id=CONN_ID)
    hook.run(CREATE_TRAINING_STATS_SQL)


def insert_training_stats(model_version: str, stat_rows: list, hook=None) -> int:
    """Store the training-data statistics of ``model_version`` (not yet the baseline).

    Re-running for the same version replaces its rows, so the task is idempotent on retry.
    """
    hook = hook or PostgresHook(postgres_conn_id=CONN_ID)
    ensure_training_stats_table(hook)
    hook.run("DELETE FROM training_stats WHERE model_version = %s", parameters=(model_version,))
    rows = [
        (
            model_version, False, r["feature_name"], r["feature_type"], r.get("category"),
            r.get("mean"), r.get("std"), r.get("min_value"), r.get("max_value"),
            r.get("proportion"), r.get("n_rows"),
        )
        for r in stat_rows
    ]
    if rows:
        hook.insert_rows(table="training_stats", rows=rows, target_fields=TRAINING_STATS_FIELDS)
    return len(rows)


def mark_baseline(model_version: str, hook=None) -> None:
    """Make ``model_version`` the only drift baseline (called when it is promoted to champion)."""
    hook = hook or PostgresHook(postgres_conn_id=CONN_ID)
    hook.run(
        "UPDATE training_stats SET is_baseline = (model_version = %s)",
        parameters=(model_version,),
    )
