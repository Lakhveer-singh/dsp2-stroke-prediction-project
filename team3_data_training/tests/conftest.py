import os
from pathlib import Path

# gx_helpers.py defaults GX_CONTEXT_ROOT_DIR to the Docker-container path
# (/opt/airflow/great_expectations/gx), which doesn't exist when tests run
# outside Docker. Point it at team4's GX project by relative path so
# `pytest tests/` works locally and in CI without any manual setup, unless
# the caller has already set it explicitly (e.g. to test a different
# checkout).
os.environ.setdefault(
    "GX_CONTEXT_ROOT_DIR",
    str(
        Path(__file__).resolve().parents[2]
        / "team4_great_expectation"
        / "great_expectations"
        / "gx"
    ),
)
