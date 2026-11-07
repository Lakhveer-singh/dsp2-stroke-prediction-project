import argparse

import numpy as np
import pandas as pd

DEFAULT_PROBABILITIES = {
    "null": 0.05,
    "range": 0.05,
    "categorical": 0.05,
    "schema": 0.02,
    "type": 0.05,
    "outlier": 0.03,
    "impossible": 0.03,
}


def inject_null(df: pd.DataFrame, p: float, rng: np.random.Generator) -> pd.DataFrame:
    """Completeness: blank out a required column (gender)."""
    df = df.copy()
    mask = rng.random(len(df)) < p
    df.loc[mask, "gender"] = None
    return df


def inject_range(df: pd.DataFrame, p: float, rng: np.random.Generator) -> pd.DataFrame:
    """Validity: age outside the valid 0-120 range."""
    df = df.copy()
    mask = rng.random(len(df)) < p
    df.loc[mask, "age"] = rng.choice([-5, 200], size=mask.sum())
    return df


def inject_categorical(df: pd.DataFrame, p: float, rng: np.random.Generator) -> pd.DataFrame:
    """Consistency: work_type value outside the 5 allowed categories."""
    df = df.copy()
    mask = rng.random(len(df)) < p
    df.loc[mask, "work_type"] = "Freelancer"
    return df


def inject_schema(df: pd.DataFrame, p: float, rng: np.random.Generator) -> pd.DataFrame:
    """Schema (file-level): drop the smoking_status column entirely."""
    if rng.random() < p:
        return df.drop(columns=["smoking_status"])
    return df


def inject_type(df: pd.DataFrame, p: float, rng: np.random.Generator) -> pd.DataFrame:
    """Type: string value in a numeric column (avg_glucose_level)."""
    df = df.copy()
    df["avg_glucose_level"] = df["avg_glucose_level"].astype(object)
    mask = rng.random(len(df)) < p
    df.loc[mask, "avg_glucose_level"] = "unknown"
    return df


def inject_outlier(df: pd.DataFrame, p: float, rng: np.random.Generator) -> pd.DataFrame:
    """Statistical outlier: avg_glucose_level far outside any plausible reading
    (clean data tops out around 270; real hyperglycemic emergencies rarely
    exceed ~350), simulating a sensor glitch or unit-conversion bug."""
    df = df.copy()
    mask = rng.random(len(df)) < p
    df.loc[mask, "avg_glucose_level"] = rng.uniform(500, 900, size=mask.sum())
    return df


def inject_impossible(df: pd.DataFrame, p: float, rng: np.random.Generator) -> pd.DataFrame:
    """Impossible values: negative bmi."""
    df = df.copy()
    mask = rng.random(len(df)) < p
    df.loc[mask, "bmi"] = -rng.uniform(1, 30, size=mask.sum())
    return df


def inject_errors(df: pd.DataFrame, probabilities: dict, seed: int = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = inject_null(df, probabilities["null"], rng)
    df = inject_range(df, probabilities["range"], rng)
    df = inject_categorical(df, probabilities["categorical"], rng)
    df = inject_type(df, probabilities["type"], rng)
    df = inject_outlier(df, probabilities["outlier"], rng)
    df = inject_impossible(df, probabilities["impossible"], rng)
    df = inject_schema(df, probabilities["schema"], rng)
    return df


def main():
    parser = argparse.ArgumentParser(description="Inject configurable data quality errors into a clean dataset.")
    parser.add_argument("--input", required=True, help="Path to the clean input CSV dataset")
    parser.add_argument("--output", required=True, help="Path to write the corrupted CSV dataset")
    parser.add_argument("--p-null", type=float, default=DEFAULT_PROBABILITIES["null"])
    parser.add_argument("--p-range", type=float, default=DEFAULT_PROBABILITIES["range"])
    parser.add_argument("--p-categorical", type=float, default=DEFAULT_PROBABILITIES["categorical"])
    parser.add_argument("--p-schema", type=float, default=DEFAULT_PROBABILITIES["schema"])
    parser.add_argument("--p-type", type=float, default=DEFAULT_PROBABILITIES["type"])
    parser.add_argument("--p-outlier", type=float, default=DEFAULT_PROBABILITIES["outlier"])
    parser.add_argument("--p-impossible", type=float, default=DEFAULT_PROBABILITIES["impossible"])
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    probabilities = {
        "null": args.p_null,
        "range": args.p_range,
        "categorical": args.p_categorical,
        "schema": args.p_schema,
        "type": args.p_type,
        "outlier": args.p_outlier,
        "impossible": args.p_impossible,
    }

    df = pd.read_csv(args.input)
    corrupted = inject_errors(df, probabilities, seed=args.seed)
    corrupted.to_csv(args.output, index=False)
    print(f"Wrote corrupted dataset to {args.output}")


if __name__ == "__main__":
    main()
