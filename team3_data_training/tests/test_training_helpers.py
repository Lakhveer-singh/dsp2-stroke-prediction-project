"""Unit tests for the training pipeline logic (dags/common/training_helpers.py).

These are the rules the Defense 2 training DAG relies on: fixed test set, label lookup without
leakage, promotion decision, drift-baseline statistics.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dags.common import training_helpers as th

REFERENCE = str(Path(__file__).resolve().parents[1] / "healthcare-dataset-stroke-data.xls")


@pytest.fixture(scope="module")
def reference():
    return th.load_reference_dataset(REFERENCE)


@pytest.fixture(scope="module")
def datasets():
    return th.build_datasets(REFERENCE, good_dir="", files=None)


@pytest.fixture(scope="module")
def model(datasets):
    return th.train_pipeline(datasets["train"])


def write_good_files(tmp_path, reference, rows_per_file=10, n_files=3, seed=0):
    """Mimic the ingestion output: feature columns only (no id / stroke label)."""
    sample = reference.sample(n=rows_per_file * n_files, random_state=seed)
    names = []
    for i in range(n_files):
        chunk = sample.iloc[i * rows_per_file:(i + 1) * rows_per_file][th.FEATURE_COLUMNS]
        name = f"good_{i}.csv"
        chunk.to_csv(tmp_path / name, index=False)
        names.append(name)
    return names, sample


# ----------------------------------------------------------------------------- data / test set
def test_reference_split_is_deterministic_and_stratified(reference):
    train_a, test_a = th.split_reference(reference)
    train_b, test_b = th.split_reference(reference)
    pd.testing.assert_frame_equal(test_a, test_b)
    pd.testing.assert_frame_equal(train_a, train_b)
    assert len(test_a) == pytest.approx(len(reference) * th.TEST_SIZE, abs=2)
    assert test_a[th.TARGET_COLUMN].mean() == pytest.approx(reference[th.TARGET_COLUMN].mean(), abs=0.005)


def test_test_set_is_the_same_whatever_good_data_arrives(tmp_path, reference):
    files, _ = write_good_files(tmp_path, reference)
    without = th.build_datasets(REFERENCE, str(tmp_path), None)["test"]
    with_new = th.build_datasets(REFERENCE, str(tmp_path), files)["test"]
    pd.testing.assert_frame_equal(without, with_new)


def test_labels_are_attached_to_good_rows(tmp_path, reference):
    files, sample = write_good_files(tmp_path, reference)
    good = th.read_good_data(str(tmp_path), files)
    labelled, unmatched = th.attach_labels(good, reference)
    assert unmatched == 0
    assert len(labelled) == len(good)
    assert labelled[th.TARGET_COLUMN].sum() == sample[th.TARGET_COLUMN].sum()


def test_rows_not_found_in_reference_are_reported_not_trained_on(tmp_path, reference):
    files, _ = write_good_files(tmp_path, reference, n_files=1)
    path = tmp_path / files[0]
    df = pd.read_csv(path)
    df.loc[0, "age"] = 12345.0  # no such row in the labelled data
    df.to_csv(path, index=False)
    labelled, unmatched = th.attach_labels(th.read_good_data(str(tmp_path), files), reference)
    assert unmatched == 1
    assert len(labelled) == 9


def test_good_rows_overlapping_the_test_set_never_reach_training(tmp_path, reference):
    _, test_df = th.split_reference(reference)
    leaked = test_df.head(10)[th.FEATURE_COLUMNS]
    leaked.to_csv(tmp_path / "leak.csv", index=False)
    result = th.build_datasets(REFERENCE, str(tmp_path), ["leak.csv"])
    assert result["info"]["n_good_rows_dropped_test_overlap"] == 10
    assert result["info"]["n_new_training_rows"] == 0
    merged = result["train"].merge(test_df[th.FEATURE_COLUMNS].drop_duplicates(), on=th.FEATURE_COLUMNS,
                                   how="inner")
    assert merged.empty


def test_good_data_extends_the_training_set(tmp_path, reference):
    base = th.build_datasets(REFERENCE, str(tmp_path), None)
    files, _ = write_good_files(tmp_path, reference, n_files=5, seed=11)
    extended = th.build_datasets(REFERENCE, str(tmp_path), files)
    assert extended["info"]["n_good_files"] == 5
    assert extended["info"]["n_train_rows"] > base["info"]["n_train_rows"]
    assert extended["info"]["n_test_rows"] == base["info"]["n_test_rows"]


def test_read_good_data_accepts_snake_case_residence_column(tmp_path, reference):
    chunk = reference.head(5)[th.FEATURE_COLUMNS].rename(columns={"Residence_type": "residence_type"})
    chunk.to_csv(tmp_path / "x.csv", index=False)
    assert "Residence_type" in th.read_good_data(str(tmp_path), ["x.csv"]).columns


# ----------------------------------------------------------------------------- model + metrics
def test_model_beats_the_trivial_classifier_on_the_fixed_test_set(model, datasets):
    metrics = th.evaluate_model(model, datasets["test"])
    assert set(metrics) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
    assert all(0.0 <= v <= 1.0 for v in metrics.values())
    assert metrics["roc_auc"] > 0.7
    assert metrics["f1"] > 0.1  # the notebook's configuration scored 0.0 here: never predicted a stroke


def test_inference_time_is_measured_in_milliseconds(model, datasets):
    ms = th.measure_inference_ms(model, datasets["test"], n_calls=5)
    assert 0 < ms < 5000


# ----------------------------------------------------------------------------- promotion rule
CAND = {"f1": 0.40, "accuracy": 0.9, "roc_auc": 0.8, "precision": 0.3, "recall": 0.6}


def test_first_run_without_champion_is_promoted():
    d = th.decide_promotion(CAND, None, "f1", inference_ms=20, threshold_ms=200)
    assert d["promote"] and "no champion" in d["reason"] and d["champion_value"] is None


def test_better_candidate_is_promoted():
    d = th.decide_promotion(CAND, {**CAND, "f1": 0.35}, "f1", 20, 200)
    assert d["promote"]


def test_equal_candidate_is_promoted_matching_is_enough():
    d = th.decide_promotion(CAND, dict(CAND), "f1", 20, 200)
    assert d["promote"]


def test_worse_candidate_is_rejected_with_reason():
    d = th.decide_promotion(CAND, {**CAND, "f1": 0.45}, "f1", 20, 200)
    assert not d["promote"]
    assert "0.4000 < champion f1=0.4500" in d["reason"]


def test_slow_candidate_is_rejected_even_if_better():
    d = th.decide_promotion({**CAND, "f1": 0.9}, CAND, "f1", inference_ms=250, threshold_ms=200)
    assert not d["promote"] and "inference time" in d["reason"]


def test_inference_time_must_be_strictly_below_threshold():
    assert not th.decide_promotion(CAND, None, "f1", 200, 200)["promote"]


def test_min_improvement_is_respected():
    champion = {**CAND, "f1": 0.39}
    assert th.decide_promotion(CAND, champion, "f1", 20, 200, min_improvement=0.0)["promote"]
    assert not th.decide_promotion(CAND, champion, "f1", 20, 200, min_improvement=0.05)["promote"]


def test_primary_metric_is_configurable():
    champion = {**CAND, "roc_auc": 0.85}
    assert th.decide_promotion(CAND, champion, "f1", 20, 200)["promote"]
    assert not th.decide_promotion(CAND, champion, "roc_auc", 20, 200)["promote"]


# ----------------------------------------------------------------------------- drift baseline stats
def test_training_stats_cover_numerical_categorical_and_prediction(model, datasets):
    stats = pd.DataFrame(th.compute_training_stats(datasets["train"], model))

    numerical = stats[stats["feature_type"] == "numerical"]
    assert set(numerical["feature_name"]) == set(th.NUMERIC_FEATURES)
    assert numerical[["mean", "std", "min_value", "max_value"]].notna().all().all()

    categorical = stats[stats["feature_type"] == "categorical"]
    assert "residence_type" in set(categorical["feature_name"])  # DB naming, not "Residence_type"
    assert "Residence_type" not in set(categorical["feature_name"])
    sums = categorical.groupby("feature_name")["proportion"].sum()
    assert np.allclose(sums, 1.0)

    prediction = stats[stats["feature_type"] == "prediction"]
    assert len(prediction) == 1
    assert 0.0 < prediction.iloc[0]["proportion"] < 1.0


def test_numerical_stats_match_the_training_data(model, datasets):
    stats = {r["feature_name"]: r for r in th.compute_training_stats(datasets["train"], model)
             if r["feature_type"] == "numerical"}
    assert stats["age"]["mean"] == pytest.approx(datasets["train"]["age"].mean())
    assert stats["bmi"]["n_rows"] == int(datasets["train"]["bmi"].notna().sum())  # NaNs not counted
