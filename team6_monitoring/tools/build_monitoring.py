"""Generates the Grafana provisioning files (dashboards + alert rules) from ONE place.

    python tools/build_monitoring.py

Writes:
  grafana/dashboards/data_quality.json          (ingested data monitoring dashboard)
  grafana/dashboards/drift_and_predictions.json (data drift + prediction issues dashboard)
  grafana/provisioning/alerting/rules.yaml      (6 alert rules, labelled for routing)

Why a generator: every panel/alert query is plain SQL kept as a Python string, so
tests/test_monitoring_sql.py can run exactly the same SQL against a real PostgreSQL.
"""
import json
import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
GRAFANA = os.path.join(os.path.dirname(HERE), "grafana")
DS = {"type": "grafana-postgresql-datasource", "uid": "dsp-postgres"}
BUCKET = "date_bin('5 minutes', {col}, TIMESTAMPTZ '2000-01-01')"

GREEN, ORANGE, RED, GREY, BLUE, YELLOW, PURPLE = "green", "orange", "red", "gray", "blue", "yellow", "purple"


def bucket(col: str) -> str:
    return BUCKET.format(col=col)


def steps(*pairs):
    """steps((None, 'green'), (10, 'orange'), (50, 'red'))"""
    return [{"color": color, "value": value} for value, color in pairs]


def target(sql: str, fmt: str = "time_series", ref: str = "A") -> dict:
    return {"datasource": DS, "editorMode": "code", "format": fmt, "rawQuery": True, "rawSql": sql.strip(),
            "refId": ref}


def timeseries(pid, title, description, sql, pos, unit="short", thresholds=None, draw="line", stack=False,
               overrides=None, minimum=None, maximum=None, fill=15):
    custom = {
        "drawStyle": draw, "lineWidth": 2, "fillOpacity": 70 if draw == "bars" else fill,
        "gradientMode": "scheme" if thresholds else "none", "showPoints": "auto", "spanNulls": True,
        "barAlignment": 0, "axisPlacement": "auto",
        "stacking": {"mode": "normal" if stack else "none", "group": "A"},
        "thresholdsStyle": {"mode": "line+area" if thresholds else "off"},
    }
    defaults = {
        "color": {"mode": "thresholds"} if thresholds else {"mode": "palette-classic"},
        "custom": custom, "unit": unit,
        "thresholds": {"mode": "absolute", "steps": thresholds or steps((None, GREEN))},
    }
    if minimum is not None:
        defaults["min"] = minimum
    if maximum is not None:
        defaults["max"] = maximum
    return {
        "id": pid, "type": "timeseries", "title": title, "description": description, "datasource": DS,
        "gridPos": {"x": pos[0], "y": pos[1], "w": pos[2], "h": pos[3]},
        "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "none"}},
        "targets": [target(sql)],
    }


def bargauge(pid, title, description, sql, pos, thresholds):
    return {
        "id": pid, "type": "bargauge", "title": title, "description": description, "datasource": DS,
        "gridPos": {"x": pos[0], "y": pos[1], "w": pos[2], "h": pos[3]},
        "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "min": 0,
                                     "thresholds": {"mode": "absolute", "steps": thresholds}}, "overrides": []},
        "options": {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                    "reduceOptions": {"values": True, "calcs": [], "fields": ""}},
        "targets": [target(sql, fmt="table")],
    }


def fixed(name, color, dash=False):
    props = [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]
    if dash:
        props.append({"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}})
    return {"matcher": {"id": "byName", "options": name}, "properties": props}


def dashboard(uid, title, description, panels, templating=None, tags=None):
    return {
        "uid": uid, "title": title, "description": description, "tags": tags or ["dsp"], "timezone": "browser",
        "schemaVersion": 39, "version": 1, "editable": True, "graphTooltip": 1, "refresh": "10s",
        "time": {"from": "now-1h", "to": "now"}, "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m"]},
        "templating": {"list": templating or []}, "annotations": {"list": []}, "links": [], "panels": panels,
    }


# =====================================================================================
# Dashboard 1 - ingested data quality (data operations team)
# =====================================================================================
# The 5 validation categories -> stored error types (see team1_airflow/dags/common/gx_helpers.py)
ERROR_CATEGORY_CASE = """CASE e.error_type
            WHEN 'null_required_field' THEN 'completeness'
            WHEN 'value_out_of_range' THEN 'validity'
            WHEN 'impossible_value' THEN 'validity'
            WHEN 'statistical_outlier' THEN 'validity'
            WHEN 'invalid_categorical_value' THEN 'consistency'
            WHEN 'wrong_type_value' THEN 'type'
            ELSE 'other' END"""
REJECTED_ROWS = "CASE WHEN missing_column THEN total_rows ELSE invalid_rows END"

DQ_SQL = {
    "invalid_pct": """
SELECT run_timestamp AS "time",
       CASE WHEN missing_column THEN 100.0 ELSE invalid_percentage END AS "invalid % per ingested file"
FROM ingestion_stats
WHERE $__timeFilter(run_timestamp)
ORDER BY 1""",
    "errors_by_category": f"""
WITH errs AS (
  SELECT s.run_timestamp AS ts,
         {ERROR_CATEGORY_CASE} AS category,
         e.error_count::float AS cnt
  FROM ingestion_stats s
  JOIN ingestion_error_types e ON e.ingestion_stat_id = s.id
  WHERE $__timeFilter(s.run_timestamp)
  UNION ALL
  SELECT run_timestamp, 'schema (files)', 1.0
  FROM ingestion_stats
  WHERE missing_column AND $__timeFilter(run_timestamp)
)
SELECT {bucket('ts')} AS "time", category AS metric, SUM(cnt) AS "value"
FROM errs
GROUP BY 1, 2
ORDER BY 1""",
    "criticality": f"""
SELECT {bucket('run_timestamp')} AS "time", criticality AS metric, COUNT(*)::float AS "value"
FROM ingestion_stats
WHERE $__timeFilter(run_timestamp)
GROUP BY 1, 2
ORDER BY 1""",
    "rejected_share": f"""
SELECT {bucket('run_timestamp')} AS "time",
       100.0 * SUM({REJECTED_ROWS}) / NULLIF(SUM(total_rows), 0) AS "rejected rows %"
FROM ingestion_stats
WHERE $__timeFilter(run_timestamp)
GROUP BY 1
ORDER BY 1""",
    "top_errors": f"""
SELECT {ERROR_CATEGORY_CASE} || ' / ' || e.error_type AS "error type",
       SUM(e.error_count) AS "rows affected"
FROM ingestion_stats s
JOIN ingestion_error_types e ON e.ingestion_stat_id = s.id
WHERE $__timeFilter(s.run_timestamp)
GROUP BY e.error_type
ORDER BY 2 DESC
LIMIT 8""",
    "schema_errors": f"""
SELECT {bucket('run_timestamp')} AS "time",
       COUNT(*) FILTER (WHERE missing_column)::float AS "files with a missing column"
FROM ingestion_stats
WHERE $__timeFilter(run_timestamp)
GROUP BY 1
ORDER BY 1""",
}

PCT_THRESHOLDS = steps((None, GREEN), (10, ORANGE), (50, RED))  # same cut-offs as the criticality levels


def data_quality_dashboard() -> dict:
    panels = [
        timeseries(1, "Invalid data % per ingested file (completeness, validity, consistency, type, schema)",
                   "One point per ingestion run. A file with a missing column counts as 100 %. "
                   "Colours follow the criticality levels: green < 10 %, orange 10-50 %, red >= 50 %.",
                   DQ_SQL["invalid_pct"], (0, 0, 12, 8), unit="percent", thresholds=PCT_THRESHOLDS,
                   minimum=0, maximum=100),
        timeseries(2, "Errors by validation category over time (5 min buckets)",
                   "Rows affected per category: completeness = null required fields, validity = out-of-range / "
                   "impossible / outlier values, consistency = unknown categories, type = wrong data type. "
                   "'schema (files)' counts files with a missing column (one per file).",
                   DQ_SQL["errors_by_category"], (12, 0, 12, 8), draw="bars", stack=True, unit="short",
                   overrides=[fixed("completeness", BLUE), fixed("validity", PURPLE),
                              fixed("consistency", YELLOW), fixed("type", ORANGE),
                              fixed("schema (files)", RED), fixed("other", GREY)]),
        timeseries(3, "Ingestion criticality over time (files per 5 min)",
                   "How many ingested files fell in each criticality level (spec: low <= 10 %, medium <= 50 %, "
                   "high > 50 % invalid rows or missing column).",
                   DQ_SQL["criticality"], (0, 8, 12, 8), draw="bars", stack=True,
                   overrides=[fixed("none", GREEN), fixed("low", YELLOW), fixed("medium", ORANGE),
                              fixed("high", RED)]),
        timeseries(4, "Share of rejected rows (5 min buckets)",
                   "Invalid rows / all ingested rows per 5 minutes (missing-column files count entirely). "
                   "Rising values = the data source is getting worse.",
                   DQ_SQL["rejected_share"], (12, 8, 12, 8), unit="percent", thresholds=PCT_THRESHOLDS,
                   minimum=0, maximum=100),
        bargauge(5, "Most frequent error types in the selected window (rows affected)",
                 "Which error types dominate recent ingestions (dashboard time range, default 1 h).",
                 DQ_SQL["top_errors"], (0, 16, 12, 8), steps((None, GREEN), (10, ORANGE), (30, RED))),
        timeseries(6, "Schema errors: files with a missing column (5 min buckets)",
                   "Schema errors are file-level problems (a required column is absent). "
                   "Any value > 0 deserves attention; 2+ in 10 minutes raises an alert.",
                   DQ_SQL["schema_errors"], (12, 16, 12, 8), draw="bars", unit="short",
                   thresholds=steps((None, GREEN), (1, ORANGE), (3, RED)), minimum=0),
    ]
    return dashboard("dsp-data-quality", "DSP | Ingested data quality",
                     "Data operations: quality of the files ingested by the ingestion DAG (last hour, auto-refresh).",
                     panels, tags=["dsp", "data-quality"])


# =====================================================================================
# Dashboard 2 - data drift & prediction issues (ML engineers)
# =====================================================================================
NUM_FEATURES = ["age", "avg_glucose_level", "bmi"]
CAT_FEATURES = ["smoking_status", "work_type", "gender"]
BASELINE = "is_baseline"  # training_stats rows of the promoted (champion) model only

_Z_COLUMNS = ",\n".join(
    f"""       ABS(s.{f} - (SELECT mean FROM b WHERE feature_name = '{f}'))
         / NULLIF((SELECT std FROM b WHERE feature_name = '{f}') / SQRT(s.n), 0) AS "{f}" """
    for f in NUM_FEATURES)
_UNPIVOT = "\n  UNION ALL\n".join(
    f"""  SELECT {bucket('prediction_time')} AS time, '{f}' AS feature, {f}::text AS category
  FROM predictions WHERE $__timeFilter(prediction_time)"""
    for f in CAT_FEATURES)
_CAT_LIST = ", ".join("'" + f + "'" for f in CAT_FEATURES)
_RANGE_COLUMNS = ",\n".join(
    f"""       100.0 * AVG(((p.{f} < (SELECT min_value FROM b WHERE feature_name = '{f}'))
                  OR (p.{f} > (SELECT max_value FROM b WHERE feature_name = '{f}')))::int) AS "{f}" """
    for f in NUM_FEATURES)

ML_SQL = {
    "num_mean": f"""
SELECT {bucket('p.prediction_time')} AS "time",
       AVG(p.${{num_feature}}) AS "serving mean (5 min)",
       (SELECT mean FROM training_stats WHERE {BASELINE} AND feature_name = '${{num_feature}}') AS "training baseline"
FROM predictions p
WHERE $__timeFilter(p.prediction_time)
GROUP BY 1
ORDER BY 1""",
    "num_z": f"""
WITH b AS (
  SELECT feature_name, mean, std FROM training_stats WHERE {BASELINE} AND feature_type = 'numerical'
), s AS (
  SELECT {bucket('prediction_time')} AS time, COUNT(*)::float AS n,
         AVG(age) AS age, AVG(avg_glucose_level) AS avg_glucose_level, AVG(bmi) AS bmi
  FROM predictions
  WHERE $__timeFilter(prediction_time)
  GROUP BY 1
)
SELECT s.time AS "time",
{_Z_COLUMNS}
FROM s
ORDER BY 1""",
    "cat_tvd": f"""
WITH unpiv AS (
{_UNPIVOT}
), serv AS (
  SELECT time, feature, category, COUNT(*)::float AS n FROM unpiv GROUP BY 1, 2, 3
), tot AS (
  SELECT time, feature, SUM(n) AS total FROM serv GROUP BY 1, 2
), base AS (
  SELECT feature_name AS feature, category, proportion FROM training_stats
  WHERE {BASELINE} AND feature_type = 'categorical' AND feature_name IN ({_CAT_LIST})
), cats AS (
  SELECT feature, category FROM base UNION SELECT feature, category FROM serv
), grid AS (
  SELECT t.time, t.feature, t.total, c.category FROM tot t JOIN cats c ON c.feature = t.feature
)
SELECT g.time AS "time", g.feature AS metric,
       0.5 * SUM(ABS(COALESCE(s.n, 0) / g.total - COALESCE(b.proportion, 0))) AS "value"
FROM grid g
LEFT JOIN serv s ON s.time = g.time AND s.feature = g.feature AND s.category = g.category
LEFT JOIN base b ON b.feature = g.feature AND b.category = g.category
GROUP BY 1, 2
ORDER BY 1""",
    "out_of_range": f"""
WITH b AS (
  SELECT feature_name, min_value, max_value FROM training_stats WHERE {BASELINE} AND feature_type = 'numerical'
)
SELECT {bucket('p.prediction_time')} AS "time",
{_RANGE_COLUMNS}
FROM predictions p
WHERE $__timeFilter(p.prediction_time)
GROUP BY 1
ORDER BY 1""",
    "pos_rate": f"""
SELECT {bucket('prediction_time')} AS "time",
       AVG(prediction)::float AS "serving positive rate (5 min)",
       (SELECT proportion FROM training_stats WHERE {BASELINE} AND feature_name = 'prediction') AS "training baseline"
FROM predictions
WHERE $__timeFilter(prediction_time)
GROUP BY 1
ORDER BY 1""",
    "proba_bands": f"""
SELECT {bucket('prediction_time')} AS "time",
       (COUNT(*) FILTER (WHERE prediction_proba < 0.2))::float / COUNT(*) AS "p < 0.2",
       (COUNT(*) FILTER (WHERE prediction_proba >= 0.2
                         AND prediction_proba < 0.5))::float / COUNT(*) AS "0.2 <= p < 0.5",
       (COUNT(*) FILTER (WHERE prediction_proba >= 0.5))::float / COUNT(*) AS "p >= 0.5"
FROM predictions
WHERE $__timeFilter(prediction_time)
GROUP BY 1
ORDER BY 1""",
    "proba_spread": f"""
SELECT {bucket('prediction_time')} AS "time", STDDEV_SAMP(prediction_proba) AS "std of predicted probability"
FROM predictions
WHERE $__timeFilter(prediction_time)
GROUP BY 1
HAVING COUNT(*) >= 5
ORDER BY 1""",
    "by_version": f"""
SELECT {bucket('prediction_time')} AS "time", model_version AS metric, AVG(prediction)::float AS "value"
FROM predictions
WHERE $__timeFilter(prediction_time)
GROUP BY 1, 2
ORDER BY 1""",
}


def drift_dashboard() -> dict:
    variable = {
        "name": "num_feature", "label": "Numerical feature", "type": "custom", "query": ",".join(NUM_FEATURES),
        "current": {"selected": True, "text": "age", "value": "age"},
        "options": [{"selected": f == "age", "text": f, "value": f} for f in NUM_FEATURES],
        "multi": False, "includeAll": False, "hide": 0,
    }
    panels = [
        timeseries(1, "Numerical feature drift: serving mean vs training baseline (pick the feature above)",
                   "Mean of the selected numerical feature in the predictions table (5 min buckets) against the "
                   "mean of the CHAMPION model's training data (dashed).",
                   ML_SQL["num_mean"], (0, 0, 12, 8), fill=10,
                   overrides=[fixed("training baseline", GREY, dash=True), fixed("serving mean (5 min)", BLUE)]),
        timeseries(2, "Numerical drift score (z-score of the 5 min mean vs training baseline)",
                   "|serving mean - training mean| / (training std / sqrt(n)). Green < 2, orange 2-3, red >= 3: "
                   "a value >= 3 means the mean moved far more than sampling noise explains.",
                   ML_SQL["num_z"], (12, 0, 12, 8), thresholds=steps((None, GREEN), (2, ORANGE), (3, RED)),
                   minimum=0),
        timeseries(3, "Categorical drift: distance to the training category shares (smoking_status, work_type, gender)",
                   "Total variation distance = 0.5 * sum |serving share - training share| per 5 min bucket "
                   "(0 = identical, 1 = completely different). Green < 0.2, orange 0.2-0.35, red >= 0.35.",
                   ML_SQL["cat_tvd"], (0, 8, 12, 8), thresholds=steps((None, GREEN), (0.2, ORANGE), (0.35, RED)),
                   minimum=0, maximum=1),
        timeseries(4, "Share of serving values outside the training range (age, glucose, bmi)",
                   "Percentage of predictions whose feature value is below the training minimum or above the "
                   "training maximum. Green < 5 %, orange 5-20 %, red >= 20 %.",
                   ML_SQL["out_of_range"], (12, 8, 12, 8), unit="percent",
                   thresholds=steps((None, GREEN), (5, ORANGE), (20, RED)), minimum=0, maximum=100),
        timeseries(5, "Positive-prediction rate: serving vs training baseline",
                   "Share of predictions = 1 (stroke) per 5 min against the share the champion model predicted "
                   "on its own training data (dashed). A large gap = model behaviour has shifted.",
                   ML_SQL["pos_rate"], (0, 16, 12, 8), unit="percentunit", minimum=0, maximum=1, fill=10,
                   overrides=[fixed("training baseline", GREY, dash=True),
                              fixed("serving positive rate (5 min)", BLUE)]),
        timeseries(6, "Predicted probability distribution over time",
                   "Share of predictions per probability band (stacked to 100 %). Watch for one band swallowing "
                   "all the others (model collapsing to one outcome).",
                   ML_SQL["proba_bands"], (12, 16, 12, 8), draw="bars", stack=True, unit="percentunit", maximum=1,
                   overrides=[fixed("p < 0.2", GREEN), fixed("0.2 <= p < 0.5", ORANGE), fixed("p >= 0.5", RED)]),
        timeseries(7, "Constant-prediction detector: spread of predicted probabilities",
                   "Standard deviation of the predicted probability per 5 min. Red (< 0.02) = the model outputs "
                   "almost the same value for everyone, orange < 0.05, green otherwise.",
                   ML_SQL["proba_spread"], (0, 24, 12, 8),
                   thresholds=steps((None, RED), (0.02, ORANGE), (0.05, GREEN)), minimum=0),
        timeseries(8, "Positive-prediction rate per model version (before / after retraining)",
                   "One line per model_version stored with each prediction: shows how behaviour changed when a "
                   "newly trained champion was promoted.",
                   ML_SQL["by_version"], (12, 24, 12, 8), unit="percentunit", minimum=0, maximum=1, fill=5),
    ]
    return dashboard("dsp-drift-predictions", "DSP | Data drift & prediction monitoring",
                     "ML engineers: serving data vs the champion model's training baseline, and model behaviour "
                     "over time (last hour, auto-refresh).", panels, templating=[variable], tags=["dsp", "ml", "drift"])


# =====================================================================================
# Alert rules (Grafana unified alerting, provisioned)
# =====================================================================================
_GREATEST = ",\n               ".join(
    f"""ABS(s.{f} - (SELECT mean FROM b WHERE feature_name = '{f}'))
                / NULLIF((SELECT std FROM b WHERE feature_name = '{f}') / SQRT(s.n), 0)"""
    for f in NUM_FEATURES)

ALERT_SQL = {
    "dq_invalid_rate": f"""
SELECT NOW() AS time,
       100.0 * SUM({REJECTED_ROWS}) / NULLIF(SUM(total_rows), 0) AS value
FROM ingestion_stats
WHERE run_timestamp > NOW() - INTERVAL '10 minutes'
HAVING COUNT(*) >= 2""",
    "dq_schema_errors": """
SELECT NOW() AS time, (COUNT(*) FILTER (WHERE missing_column))::float AS value
FROM ingestion_stats
WHERE run_timestamp > NOW() - INTERVAL '10 minutes'""",
    "dq_high_criticality": """
SELECT NOW() AS time, (COUNT(*) FILTER (WHERE criticality = 'high'))::float AS value
FROM ingestion_stats
WHERE run_timestamp > NOW() - INTERVAL '10 minutes'""",
    "ml_numeric_drift": f"""
WITH b AS (
  SELECT feature_name, mean, std FROM training_stats WHERE {BASELINE} AND feature_type = 'numerical'
), s AS (
  SELECT COUNT(*)::float AS n, AVG(age) AS age, AVG(avg_glucose_level) AS avg_glucose_level, AVG(bmi) AS bmi
  FROM predictions
  WHERE prediction_time > NOW() - INTERVAL '15 minutes'
)
SELECT NOW() AS time,
       GREATEST({_GREATEST}) AS value
FROM s
WHERE s.n >= 15""",
    "ml_constant_predictions": """
SELECT NOW() AS time, STDDEV_SAMP(prediction_proba) AS value
FROM predictions
WHERE prediction_time > NOW() - INTERVAL '10 minutes'
HAVING COUNT(*) >= 20""",
    "ml_positive_rate_shift": f"""
SELECT NOW() AS time,
       ABS(AVG(prediction)::float
           - (SELECT proportion FROM training_stats WHERE {BASELINE} AND feature_name = 'prediction')) AS value
FROM predictions
WHERE prediction_time > NOW() - INTERVAL '15 minutes'
HAVING COUNT(*) >= 20""",
}


def rule(uid, title, sql, window_s, op, threshold, team, severity, summary, description, hold="0s"):
    return {
        "uid": uid, "title": title, "condition": "C", "for": hold,
        "noDataState": "OK", "execErrState": "OK", "isPaused": False,
        "data": [
            {"refId": "A", "relativeTimeRange": {"from": window_s, "to": 0}, "datasourceUid": "dsp-postgres",
             "model": {"refId": "A", "datasource": DS, "editorMode": "code", "format": "time_series",
                       "rawQuery": True, "rawSql": sql.strip(), "intervalMs": 1000, "maxDataPoints": 43200}},
            {"refId": "B", "datasourceUid": "__expr__",
             "model": {"refId": "B", "type": "reduce", "expression": "A", "reducer": "last",
                       "settings": {"mode": "dropNN"}, "datasource": {"type": "__expr__", "uid": "__expr__"}}},
            {"refId": "C", "datasourceUid": "__expr__",
             "model": {"refId": "C", "type": "threshold", "expression": "B",
                       "conditions": [{"evaluator": {"type": op, "params": [threshold]}}],
                       "datasource": {"type": "__expr__", "uid": "__expr__"}}},
        ],
        "annotations": {"summary": summary, "description": description},
        "labels": {"team": team, "severity": severity},
    }


def alert_rules() -> dict:
    dq = [
        rule("dq-invalid-rate", "Data quality: most recent ingested rows are invalid", ALERT_SQL["dq_invalid_rate"],
             900, "gt", 50, "data_quality", "critical",
             "More than 50% of rows ingested in the last 10 minutes were rejected",
             "Share of rejected rows over the last 10 minutes (>= 2 files) exceeds 50%. Check the data source and "
             "the Data Docs reports linked in the Airflow alerts."),
        rule("dq-schema-errors", "Data quality: repeated schema errors (missing column)",
             ALERT_SQL["dq_schema_errors"], 900, "gt", 1, "data_quality", "critical",
             "2 or more files with a missing column in the last 10 minutes",
             "The upstream producer probably changed its file format: a required column is absent."),
        rule("dq-high-criticality", "Data quality: several high-criticality ingestions",
             ALERT_SQL["dq_high_criticality"], 900, "gt", 2, "data_quality", "warning",
             "3 or more high-criticality ingestions in the last 10 minutes",
             "Files with > 50% invalid rows (or a missing column) keep arriving."),
    ]
    ml = [
        rule("ml-numeric-drift", "ML: significant numerical drift vs training baseline", ALERT_SQL["ml_numeric_drift"],
             1200, "gt", 3, "ml", "critical",
             "A numerical feature mean drifted (z-score > 3) over the last 15 minutes",
             "The largest z-score of age / avg_glucose_level / bmi (serving mean vs the champion's training "
             "baseline) is above 3 with >= 15 predictions. Consider retraining."),
        rule("ml-constant-predictions", "ML: model outputs (almost) constant predictions",
             ALERT_SQL["ml_constant_predictions"], 900, "lt", 0.01, "ml", "critical",
             "Predicted probabilities have (almost) no variation in the last 10 minutes",
             "Standard deviation of prediction_proba < 0.01 over >= 20 predictions: the model collapsed to a "
             "single outcome or inputs are degenerate."),
        rule("ml-positive-rate-shift", "ML: positive-prediction rate far from training baseline",
             ALERT_SQL["ml_positive_rate_shift"], 1200, "gt", 0.25, "ml", "warning",
             "Positive-prediction rate moved more than 25 points from the baseline (15 min window)",
             "The model predicts stroke far more (or less) often than it did on its training data."),
    ]
    groups = [
        {"orgId": 1, "name": "data-quality", "folder": "DSP Alerts", "interval": "1m", "rules": dq},
        {"orgId": 1, "name": "ml-monitoring", "folder": "DSP Alerts", "interval": "1m", "rules": ml},
    ]
    return {"apiVersion": 1, "groups": groups}


def main() -> None:
    outputs = {
        os.path.join(GRAFANA, "dashboards", "data_quality.json"): data_quality_dashboard(),
        os.path.join(GRAFANA, "dashboards", "drift_and_predictions.json"): drift_dashboard(),
    }
    for path, content in outputs.items():
        with open(path, "w") as fh:
            json.dump(content, fh, indent=2)
            fh.write("\n")
        print("wrote", os.path.relpath(path, os.path.dirname(HERE)))
    rules_path = os.path.join(GRAFANA, "provisioning", "alerting", "rules.yaml")
    with open(rules_path, "w") as fh:
        fh.write("# GENERATED by tools/build_monitoring.py -- edit the generator, not this file.\n")
        yaml.safe_dump(alert_rules(), fh, sort_keys=False, width=200)
    print("wrote", os.path.relpath(rules_path, os.path.dirname(HERE)))


if __name__ == "__main__":
    main()
