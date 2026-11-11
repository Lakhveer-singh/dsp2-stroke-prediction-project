from airflow.providers.postgres.hooks.postgres import PostgresHook

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
