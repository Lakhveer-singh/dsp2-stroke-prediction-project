import argparse
import os

import pandas as pd

ROWS_PER_FILE = 10
LABEL_COLUMN = "stroke"
ID_COLUMN = "id"


def split_into_files(df: pd.DataFrame, num_files: int, output_dir: str, seed: int = None) -> None:
    """Split df into num_files CSV files of exactly ROWS_PER_FILE rows each, written to output_dir."""
    rows_needed = num_files * ROWS_PER_FILE

    if len(df) < rows_needed:
        df = df.sample(n=rows_needed, replace=True, random_state=seed)
    else:
        df = df.sample(n=rows_needed, replace=False, random_state=seed)

    df = df.reset_index(drop=True)
    df = df.drop(columns=[c for c in (LABEL_COLUMN, ID_COLUMN) if c in df.columns])

    os.makedirs(output_dir, exist_ok=True)
    for i in range(num_files):
        chunk = df.iloc[i * ROWS_PER_FILE: (i + 1) * ROWS_PER_FILE]
        chunk.to_csv(os.path.join(output_dir, f"file_{i:03d}.csv"), index=False)


def main():
    parser = argparse.ArgumentParser(description="Split a dataset into fixed-size (10 rows) inference files.")
    parser.add_argument("--input", required=True, help="Path to the input CSV dataset")
    parser.add_argument("--output-dir", required=True, help="Directory to write the split files to (e.g. raw_data)")
    parser.add_argument("--num-files", required=True, type=int, help="Number of files to generate")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for shuffling/sampling")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    split_into_files(df, args.num_files, args.output_dir, seed=args.seed)
    print(f"Wrote {args.num_files} files of {ROWS_PER_FILE} rows each to {args.output_dir}")


if __name__ == "__main__":
    main()
