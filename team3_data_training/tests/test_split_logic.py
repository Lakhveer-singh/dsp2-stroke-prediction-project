import glob
import os

import pandas as pd
import pytest

from scripts.split_dataset import split_into_files


def make_df(n_rows):
    return pd.DataFrame(
        {
            "id": range(n_rows),
            "gender": ["Male"] * n_rows,
            "age": range(n_rows),
            "avg_glucose_level": [90.0] * n_rows,
            "bmi": [25.0] * n_rows,
            "stroke": [0] * n_rows,
        }
    )


@pytest.mark.parametrize("num_files", [1, 3, 30])
def test_each_file_has_exactly_10_rows(tmp_path, num_files):
    df = make_df(500)
    output_dir = tmp_path / "raw_data"
    split_into_files(df, num_files, str(output_dir), seed=1)

    files = sorted(glob.glob(os.path.join(output_dir, "*.csv")))
    assert len(files) == num_files
    for f in files:
        assert len(pd.read_csv(f)) == 10


def test_output_files_have_no_label_or_id_column(tmp_path):
    df = make_df(100)
    output_dir = tmp_path / "raw_data"
    split_into_files(df, 5, str(output_dir), seed=1)

    for f in glob.glob(os.path.join(output_dir, "*.csv")):
        columns = pd.read_csv(f).columns
        assert "stroke" not in columns
        assert "id" not in columns


def test_handles_input_smaller_than_requested_rows(tmp_path):
    df = make_df(5)  # fewer rows than 3 files * 10 rows needed
    output_dir = tmp_path / "raw_data"
    split_into_files(df, 3, str(output_dir), seed=1)

    files = sorted(glob.glob(os.path.join(output_dir, "*.csv")))
    assert len(files) == 3
    for f in files:
        assert len(pd.read_csv(f)) == 10
