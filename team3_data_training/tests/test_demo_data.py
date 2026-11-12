"""The demo files must produce the criticality / behaviour promised in the demo script."""
from pathlib import Path

import pandas as pd
import pytest

from dags.common.gx_helpers import run_validation
from scripts import generate_demo_data

REFERENCE = Path(__file__).resolve().parents[1] / "healthcare-dataset-stroke-data.xls"


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    generate_demo_data.generate(pd.read_csv(REFERENCE), str(out), n_drift=3, seed=42)
    return out


def validate(demo_dir, name):
    return run_validation(pd.read_csv(demo_dir / name))


def test_all_files_are_ten_rows_without_label(demo_dir):
    for path in demo_dir.glob("*.csv"):
        df = pd.read_csv(path)
        assert len(df) == 10, path.name
        assert "stroke" not in df.columns and "id" not in df.columns


@pytest.mark.parametrize("name", ["demo_01_clean.csv", "demo_02_clean.csv", "demo_03_clean.csv"])
def test_clean_files_have_no_errors(demo_dir, name):
    result = validate(demo_dir, name)
    assert result["invalid_rows"] == 0 and result["criticality"] == "none"


def test_mixed_file_is_medium_with_three_invalid_rows(demo_dir):
    result = validate(demo_dir, "demo_04_mixed.csv")
    assert result["invalid_rows"] == 3 and result["criticality"] == "medium"


def test_all_errors_file_is_high_with_every_row_invalid(demo_dir):
    result = validate(demo_dir, "demo_05_all_errors.csv")
    assert result["invalid_rows"] == 10 and result["criticality"] == "high"


def test_missing_column_file_is_a_high_schema_error(demo_dir):
    result = validate(demo_dir, "demo_06_missing_column.csv")
    assert result["missing_column"] is True and result["criticality"] == "high"


def test_drift_files_pass_validation_but_are_clearly_shifted(demo_dir):
    for path in sorted(demo_dir.glob("drift_*.csv")):
        assert validate(demo_dir, path.name)["criticality"] == "none", path.name
    drift = pd.concat([pd.read_csv(p) for p in demo_dir.glob("drift_*.csv")])
    reference = pd.read_csv(REFERENCE)
    assert drift["age"].mean() > reference["age"].mean() + 20
    assert drift["avg_glucose_level"].mean() > reference["avg_glucose_level"].mean() + 40
    assert (drift["smoking_status"] == "smokes").mean() > 0.6


# ----------------------------------------------------------------------------- traffic simulator
def test_simulator_phases_cover_the_whole_run_and_end_with_drift():
    from scripts import simulate_traffic as sim

    assert sim.phase_at(0.0)[0] == "normal"
    assert sim.phase_at(0.45)[0] == "bad-data burst"
    assert sim.phase_at(0.99)[0] == "drift"
    assert sim.phase_at(5.0)[0] == "drift"  # never falls off the end


def test_simulator_builds_every_kind_of_file(tmp_path):
    import numpy as np

    from scripts import simulate_traffic as sim

    features = pd.read_csv(REFERENCE).drop(columns=["stroke", "id"])
    rng = np.random.default_rng(1)
    expectations = {"clean": ("none", 0), "mixed": ("medium", 3), "all_errors": ("high", 10)}
    for kind, (criticality, invalid) in expectations.items():
        result = run_validation(sim.build_file(kind, features, rng))
        assert result["criticality"] == criticality and result["invalid_rows"] == invalid, kind
    assert run_validation(sim.build_file("missing_column", features, rng))["missing_column"] is True
    assert run_validation(sim.build_file("drift", features, rng))["criticality"] == "none"


def test_simulator_probabilities_are_respected():
    import numpy as np

    from scripts import simulate_traffic as sim

    rng = np.random.default_rng(0)
    picks = [sim.pick_kind({"clean": 0.9, "all_errors": 0.1}, rng) for _ in range(2000)]
    assert 0.85 < picks.count("clean") / len(picks) < 0.95
