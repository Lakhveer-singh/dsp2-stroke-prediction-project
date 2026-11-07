import os

import great_expectations as gx
import pandas as pd

# In the docker-compose deployment, team4's GX project is mounted at
# /opt/airflow/great_expectations, with the context root (great_expectations.yml)
# living in its "gx" subfolder. Overridable so tests/local runs can point at a
# different checkout.
GX_CONTEXT_ROOT_DIR = os.environ.get(
    "GX_CONTEXT_ROOT_DIR", "/opt/airflow/great_expectations/gx"
)
CHECKPOINT_NAME = "stroke_checkpoint"

# Data Docs are served by the nginx container. Alerts link to this *browser-reachable*
# base URL (not the file:// path GX reports inside the Airflow container).
DATA_DOCS_PUBLIC_URL = os.environ.get("DATA_DOCS_PUBLIC_URL", "http://localhost:8081").rstrip("/")
_SITE_MARKER = "local_site/"

_context = None


def _get_context():
    global _context
    if _context is None:
        _context = gx.get_context(context_root_dir=GX_CONTEXT_ROOT_DIR)
    return _context


def _error_category(expectation_type: str, column: str | None) -> str:
    if expectation_type == "expect_column_values_to_not_be_null":
        return "null_required_field"
    if expectation_type == "expect_column_values_to_be_between":
        if column == "bmi":
            return "impossible_value"
        if column == "avg_glucose_level":
            return "statistical_outlier"
        return "value_out_of_range"
    if expectation_type == "expect_column_values_to_be_in_set":
        return "invalid_categorical_value"
    if expectation_type == "expect_column_values_to_be_of_type":
        return "wrong_type_value"
    return expectation_type


def calculate_criticality(missing_column: bool, invalid_percentage: float) -> str:
    if missing_column or invalid_percentage > 50:
        return "high"
    if 10 <= invalid_percentage <= 50:
        return "medium"
    if 0 < invalid_percentage < 10:
        return "low"
    return "none"


def get_data_docs_path(context=None) -> str:
    context = context or _get_context()
    sites = context.get_docs_sites_urls()
    return sites[0]["site_url"] if sites else ""


def to_public_url(site_url: str) -> str:
    """Translate a GX ``file://.../local_site/<page>`` URL into the nginx-served URL."""
    if _SITE_MARKER in site_url:
        return f"{DATA_DOCS_PUBLIC_URL}/{site_url.split(_SITE_MARKER, 1)[1]}"
    return f"{DATA_DOCS_PUBLIC_URL}/index.html"


def get_validation_report_url(context, result_identifier) -> str:
    """Public URL of the Data Docs page for one specific validation run."""
    try:
        sites = context.get_docs_sites_urls(resource_identifier=result_identifier)
        if sites:
            return to_public_url(sites[0]["site_url"])
    except Exception:  # never let a link-building problem fail the ingestion
        pass
    return to_public_url(get_data_docs_path(context))


def run_validation(df: pd.DataFrame) -> dict:
    total_rows = len(df)
    context = _get_context()
    checkpoint = context.checkpoints.get(CHECKPOINT_NAME)
    checkpoint_result = checkpoint.run(batch_parameters={"dataframe": df})
    result_identifier, validation_result = next(iter(checkpoint_result.run_results.items()))
    data_docs_path = get_data_docs_path(context)
    data_docs_url = get_validation_report_url(context, result_identifier)

    invalid_row_indices: set[int] = set()
    error_counts: dict[str, int] = {}

    for expectation_result in validation_result["results"]:
        if expectation_result["success"]:
            continue

        config = expectation_result["expectation_config"]
        expectation_type = config["type"]

        if expectation_type == "expect_table_columns_to_match_set":
            return {
                "criticality": calculate_criticality(True, 0.0),
                "total_rows": total_rows,
                "invalid_rows": 0,
                "invalid_percentage": 0.0,
                "missing_column": True,
                "error_counts": {},
                "invalid_row_indices": [],
                "data_docs_path": data_docs_path,
                "data_docs_url": data_docs_url,
            }

        result = expectation_result["result"]
        # Column-level type mismatches (e.g. a stray string forces the whole
        # pandas column to object dtype) don't always report unexpected_count /
        # partial_unexpected_index_list, since GX can't attribute the failure to
        # specific rows. Treat every row as suspect in that case.
        unexpected_count = result.get("unexpected_count", total_rows)
        indices = result.get("partial_unexpected_index_list") or list(df.index)
        invalid_row_indices.update(indices)

        category = _error_category(expectation_type, config["kwargs"].get("column"))
        error_counts[category] = error_counts.get(category, 0) + unexpected_count

    invalid_rows = len(invalid_row_indices)
    invalid_percentage = (invalid_rows / total_rows * 100) if total_rows else 0.0

    return {
        "criticality": calculate_criticality(False, invalid_percentage),
        "total_rows": total_rows,
        "invalid_rows": invalid_rows,
        "invalid_percentage": invalid_percentage,
        "missing_column": False,
        "error_counts": error_counts,
        "invalid_row_indices": sorted(invalid_row_indices),
        "data_docs_path": data_docs_path,
        "data_docs_url": data_docs_url,
    }
