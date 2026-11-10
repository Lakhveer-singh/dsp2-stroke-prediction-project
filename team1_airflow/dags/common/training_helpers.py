"""Pure data / model logic of the training pipeline (no Airflow, no MLflow imports).

Kept free of orchestration code so it can be unit tested directly (see
team3_data_training/tests/test_training_helpers.py) and reused by the bootstrap script.

Where the labels come from
--------------------------
Files that reach ``good_data`` are *inference* files: the label (``stroke``) and ``id`` were
dropped when they were generated (team3 ``split_dataset.py``). Ground truth normally arrives
later in production; we simulate that "delayed label feedback" by looking the labels up in the
labelled reference dataset (the rows were sampled from it and validated rows are unmodified).

Where the test set comes from (fair champion/candidate comparison)
-------------------------------------------------------------------
A fixed, stratified 20 % hold-out of the reference dataset (constant seed -> always the same
rows). Both the candidate and the current champion are scored on exactly this set, and any
``good_data`` row that matches a test row is removed from the training data (no leakage).
"""
import os
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

NUMERIC_FEATURES = ["age", "avg_glucose_level", "bmi"]
CATEGORICAL_FEATURES = ["gender", "ever_married", "work_type", "Residence_type", "smoking_status"]
PASSTHROUGH_FEATURES = ["hypertension", "heart_disease"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES + PASSTHROUGH_FEATURES
TARGET_COLUMN = "stroke"

TEST_SIZE = 0.2
SPLIT_SEED = 42

# Training-time column names differ in casing from the API / database names for one column.
DB_FEATURE_NAME = {"Residence_type": "residence_type"}

PRIMARY_METRICS = ("f1", "accuracy", "roc_auc", "precision", "recall")


# ------------------------------------------------------------------ data
def load_reference_dataset(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df[FEATURE_COLUMNS + [TARGET_COLUMN]].reset_index(drop=True)


def split_reference(reference: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministic stratified split -> (train_part, fixed_test_set)."""
    train_df, test_df = train_test_split(
        reference, test_size=TEST_SIZE, stratify=reference[TARGET_COLUMN], random_state=SPLIT_SEED
    )
    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)


def list_good_files(good_dir: str) -> List[str]:
    if not os.path.isdir(good_dir):
        return []
    return sorted(f for f in os.listdir(good_dir) if f.endswith(".csv"))


def read_good_data(good_dir: str, files: List[str]) -> pd.DataFrame:
    frames = [pd.read_csv(os.path.join(good_dir, f)) for f in files]
    if not frames:
        return pd.DataFrame(columns=FEATURE_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"residence_type": "Residence_type"})
    return df[FEATURE_COLUMNS]


def attach_labels(good_df: pd.DataFrame, reference: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Look up the ground-truth label of each good row. Returns (labelled_rows, n_unmatched)."""
    if good_df.empty:
        return good_df.assign(**{TARGET_COLUMN: pd.Series(dtype="int64")}), 0
    lookup = reference.drop_duplicates(subset=FEATURE_COLUMNS)[FEATURE_COLUMNS + [TARGET_COLUMN]]
    merged = good_df.merge(lookup, on=FEATURE_COLUMNS, how="left")
    n_unmatched = int(merged[TARGET_COLUMN].isna().sum())
    labelled = merged.dropna(subset=[TARGET_COLUMN]).copy()
    labelled[TARGET_COLUMN] = labelled[TARGET_COLUMN].astype(int)
    return labelled.reset_index(drop=True), n_unmatched


def drop_rows_present_in(df: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    """Anti-join on the feature columns (used to keep test rows out of the training data)."""
    if df.empty:
        return df
    keys = other[FEATURE_COLUMNS].drop_duplicates()
    merged = df.merge(keys, on=FEATURE_COLUMNS, how="left", indicator=True)
    return merged[merged["_merge"] == "left_only"].drop(columns="_merge").reset_index(drop=True)


def build_datasets(reference_path: str, good_dir: str, files: Optional[List[str]] = None) -> Dict:
    """Training set = reference train part + labelled good_data rows (minus test rows).

    ``files=None`` -> only the reference data (used for the very first, bootstrap model).
    """
    reference = load_reference_dataset(reference_path)
    train_ref, test_df = split_reference(reference)

    new_rows = pd.DataFrame(columns=FEATURE_COLUMNS + [TARGET_COLUMN])
    n_good_rows = n_unmatched = n_leaky = 0
    if files:
        good_df = read_good_data(good_dir, files)
        n_good_rows = len(good_df)
        labelled, n_unmatched = attach_labels(good_df, reference)
        new_rows = drop_rows_present_in(labelled, test_df)
        n_leaky = len(labelled) - len(new_rows)

    train_df = pd.concat([train_ref, new_rows], ignore_index=True) if len(new_rows) else train_ref
    info = {
        "n_reference_train_rows": len(train_ref),
        "n_good_files": len(files or []),
        "n_good_rows": n_good_rows,
        "n_good_rows_unlabelled": n_unmatched,
        "n_good_rows_dropped_test_overlap": n_leaky,
        "n_new_training_rows": len(new_rows),
        "n_train_rows": len(train_df),
        "n_test_rows": len(test_df),
        "test_positive_rate": float(test_df[TARGET_COLUMN].mean()),
    }
    return {"train": train_df, "test": test_df, "info": info}


# ------------------------------------------------------------------ model
def build_pipeline(n_estimators: int = 200, random_state: int = 42) -> Pipeline:
    """Preprocessing + random forest, as in the Defense 1 notebook (model_training/train_model.ipynb).

    One deliberate change: ``class_weight="balanced_subsample"`` + ``min_samples_leaf=10``.
    The notebook's forest (``balanced``, fully grown trees) practically never predicts the
    positive class on unseen data (F1 = 0 on the hold-out), which makes F1 useless as a
    promotion metric and the prediction dashboards flat. This setting reaches F1 ~ 0.34 /
    ROC-AUC ~ 0.82 on the same hold-out with ~15 % positive predictions.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ],
        remainder="passthrough",
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", RandomForestClassifier(n_estimators=n_estimators, class_weight="balanced_subsample",
                                                  min_samples_leaf=10, random_state=random_state)),
        ]
    )


def train_pipeline(train_df: pd.DataFrame) -> Pipeline:
    pipeline = build_pipeline()
    pipeline.fit(train_df[FEATURE_COLUMNS], train_df[TARGET_COLUMN])
    return pipeline


def evaluate_model(model, test_df: pd.DataFrame) -> Dict[str, float]:
    X, y = test_df[FEATURE_COLUMNS], test_df[TARGET_COLUMN]
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)[:, 1]
    return {
        "accuracy": float(accuracy_score(y, y_pred)),
        "precision": float(precision_score(y, y_pred, zero_division=0)),
        "recall": float(recall_score(y, y_pred, zero_division=0)),
        "f1": float(f1_score(y, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, y_proba)),
    }


def measure_inference_ms(model, sample: pd.DataFrame, n_calls: int = 30) -> float:
    """Mean latency (ms) of ONE single-row ``predict`` + ``predict_proba`` call.

    Single-row calls mimic what the API does for a webapp prediction; the model is warmed up
    first so one-off import/initialisation costs are not counted.
    """
    rows = [sample[FEATURE_COLUMNS].iloc[[i % len(sample)]] for i in range(n_calls)]
    model.predict(rows[0])
    start = time.perf_counter()
    for row in rows:
        model.predict(row)
        model.predict_proba(row)
    return (time.perf_counter() - start) / n_calls * 1000.0


def decide_promotion(candidate_metrics: Dict[str, float], champion_metrics: Optional[Dict[str, float]],
                     primary_metric: str, inference_ms: float, threshold_ms: float,
                     min_improvement: float = 0.0) -> Dict:
    """Promotion rule (Defense 2): candidate >= champion on the primary metric AND fast enough."""
    candidate_value = candidate_metrics[primary_metric]
    champion_value = champion_metrics[primary_metric] if champion_metrics else None
    decision = {
        "promote": False,
        "primary_metric": primary_metric,
        "candidate_value": candidate_value,
        "champion_value": champion_value,
        "inference_ms": inference_ms,
        "inference_threshold_ms": threshold_ms,
        "reason": "",
    }
    if not inference_ms < threshold_ms:
        decision["reason"] = (f"inference time {inference_ms:.1f} ms is not below the "
                              f"{threshold_ms:g} ms threshold")
        return decision
    if champion_metrics is None:
        decision["promote"] = True
        decision["reason"] = "no champion exists yet (first training run)"
        return decision
    if candidate_value >= champion_value + min_improvement:
        decision["promote"] = True
        decision["reason"] = (f"candidate {primary_metric}={candidate_value:.4f} >= "
                              f"champion {primary_metric}={champion_value:.4f}")
    else:
        decision["reason"] = (f"candidate {primary_metric}={candidate_value:.4f} < "
                              f"champion {primary_metric}={champion_value:.4f}")
    return decision


# ------------------------------------------------------------------ drift baseline
def compute_training_stats(train_df: pd.DataFrame, model) -> List[Dict]:
    """Feature + prediction statistics of the training data (the drift baseline).

    * numerical features  -> mean, std, min, max
    * categorical features -> proportion of every category
    * model predictions   -> predicted-positive rate and mean/std of the probability
    """
    rows: List[Dict] = []
    n = len(train_df)
    for col in NUMERIC_FEATURES:
        s = train_df[col].astype(float)
        rows.append({
            "feature_name": col, "feature_type": "numerical", "mean": float(s.mean()),
            "std": float(s.std()), "min_value": float(s.min()), "max_value": float(s.max()),
            "n_rows": int(s.notna().sum()),
        })
    for col in CATEGORICAL_FEATURES + PASSTHROUGH_FEATURES:
        proportions = train_df[col].astype(str).value_counts(normalize=True)
        for category, proportion in proportions.items():
            rows.append({
                "feature_name": DB_FEATURE_NAME.get(col, col), "feature_type": "categorical",
                "category": str(category), "proportion": float(proportion), "n_rows": n,
            })
    proba = model.predict_proba(train_df[FEATURE_COLUMNS])[:, 1]
    pred = model.predict(train_df[FEATURE_COLUMNS])
    rows.append({
        "feature_name": "prediction", "feature_type": "prediction", "category": "1",
        "proportion": float(np.mean(pred)), "mean": float(np.mean(proba)), "std": float(np.std(proba, ddof=1)),
        "n_rows": n,
    })
    return rows
