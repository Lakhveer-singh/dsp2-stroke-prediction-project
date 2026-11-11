"""Minimal PostgresHook stand-in (psycopg2 only).

Used where no Airflow metadata DB / connection machinery is available: the bootstrap script
and the integration tests. Implements just the two methods ``db_helpers`` calls.
"""
import psycopg2


class SimpleHook:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def run(self, sql, parameters=None):
        conn = psycopg2.connect(self.dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, parameters)
        finally:
            conn.close()

    def insert_rows(self, table, rows, target_fields):
        columns = ", ".join(target_fields)
        placeholders = ", ".join(["%s"] * len(target_fields))
        conn = psycopg2.connect(self.dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", rows)
        finally:
            conn.close()
