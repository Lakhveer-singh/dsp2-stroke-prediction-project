"""Prepare the files for the live defense demo (kept OUTSIDE data/raw_data on purpose).

    python scripts/generate_demo_data.py --input healthcare-dataset-stroke-data.xls --output-dir demo_files

Creates (10 rows each, no label column, unique file names -> never clash with raw_data files):

  demo_01_clean.csv, demo_02_clean.csv, demo_03_clean.csv   -> criticality none  (good_data)
  demo_04_mixed.csv                                          -> 3/10 invalid rows = medium (bad_data + split)
  demo_05_all_errors.csv                                     -> 10/10 invalid rows = high (bad_data)
  demo_06_missing_column.csv                                 -> schema error = high (bad_data)
  drift_01.csv ... drift_NN.csv                              -> VALID rows whose distribution is shifted
                                                                (older, higher glucose, mostly smokers,
                                                                self-employed): they pass validation, reach
                                                                the model and make the drift dashboard react.

During the demo copy them into data/raw_data/ one by one (the ingestion DAG runs every minute).
"""
import argparse
import os

import numpy as np
import pandas as pd

try:  # imported as a package (pytest from team3_data_training/)
    from scripts.inject_errors import inject_categorical, inject_null, inject_range
    from scripts.split_dataset import ID_COLUMN, LABEL_COLUMN, ROWS_PER_FILE
except ModuleNotFoundError:  # run directly: python scripts/generate_demo_data.py
    from inject_errors import inject_categorical, inject_null, inject_range
    from split_dataset import ID_COLUMN, LABEL_COLUMN, ROWS_PER_FILE

DRIFT_GLUCOSE_CAP = 340.0  # stay below the 350 validity limit: drifted rows must still be VALID


def clean_chunks(df: pd.DataFrame, n_files: int, seed: int) -> list:
    df = df.drop(columns=[c for c in (LABEL_COLUMN, ID_COLUMN) if c in df.columns])
    df = df.sample(n=n_files * ROWS_PER_FILE, random_state=seed).reset_index(drop=True)
    return [df.iloc[i * ROWS_PER_FILE:(i + 1) * ROWS_PER_FILE].copy() for i in range(n_files)]


def make_mixed(chunk: pd.DataFrame) -> pd.DataFrame:
    """Exactly 3 of 10 rows invalid (completeness, validity, consistency) -> 'medium'."""
    chunk = chunk.copy()
    chunk.loc[chunk.index[0], "gender"] = None
    chunk.loc[chunk.index[1], "age"] = 200
    chunk.loc[chunk.index[2], "work_type"] = "Freelancer"
    return chunk


def make_all_errors(chunk: pd.DataFrame) -> pd.DataFrame:
    """Every row invalid (null gender, age out of range, unknown work_type, text glucose)."""
    rng = np.random.default_rng(0)
    chunk = inject_null(chunk, 1.0, rng)
    chunk = inject_range(chunk, 1.0, rng)
    chunk = inject_categorical(chunk, 1.0, rng)
    chunk = chunk.copy()
    chunk["avg_glucose_level"] = chunk["avg_glucose_level"].astype(object)
    chunk["avg_glucose_level"] = "unknown"
    return chunk


def make_missing_column(chunk: pd.DataFrame) -> pd.DataFrame:
    return chunk.drop(columns=["smoking_status"])


def make_drifted(chunk: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Shift the distribution but keep every value individually valid."""
    chunk = chunk.copy()
    chunk["age"] = (chunk["age"] + 30).clip(upper=100)
    chunk["avg_glucose_level"] = (chunk["avg_glucose_level"] * 1.6 + 20).clip(upper=DRIFT_GLUCOSE_CAP)
    chunk["hypertension"] = 1
    chunk["smoking_status"] = np.where(rng.random(len(chunk)) < 0.8, "smokes", "formerly smoked")
    chunk["work_type"] = np.where(rng.random(len(chunk)) < 0.8, "Self-employed", "Private")
    return chunk


def generate(df: pd.DataFrame, output_dir: str, n_drift: int = 8, seed: int = 42) -> list:
    os.makedirs(output_dir, exist_ok=True)
    rng = np.random.default_rng(seed)
    chunks = clean_chunks(df, 6 + n_drift, seed)
    files = {
        "demo_01_clean.csv": chunks[0],
        "demo_02_clean.csv": chunks[1],
        "demo_03_clean.csv": chunks[2],
        "demo_04_mixed.csv": make_mixed(chunks[3]),
        "demo_05_all_errors.csv": make_all_errors(chunks[4]),
        "demo_06_missing_column.csv": make_missing_column(chunks[5]),
    }
    for i in range(n_drift):
        files[f"drift_{i + 1:02d}.csv"] = make_drifted(chunks[6 + i], rng)
    for name, frame in files.items():
        frame.to_csv(os.path.join(output_dir, name), index=False)
    return list(files)


def main():
    parser = argparse.ArgumentParser(description="Generate the live-defense demo files.")
    parser.add_argument("--input", required=True, help="Path to the clean labelled dataset")
    parser.add_argument("--output-dir", default="demo_files")
    parser.add_argument("--n-drift", type=int, default=8, help="Number of drifted (valid) files")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    names = generate(pd.read_csv(args.input), args.output_dir, args.n_drift, args.seed)
    print(f"Wrote {len(names)} demo files to {args.output_dir}: {', '.join(names)}")


if __name__ == "__main__":
    main()
