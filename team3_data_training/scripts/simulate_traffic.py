"""Feed the REAL pipeline with realistic traffic so the Grafana dashboards fill up with genuine data.

    python scripts/simulate_traffic.py --input healthcare-dataset-stroke-data.xls \
        --raw-dir data/raw_data --interval 60 --duration-min 240

It only drops one new 10-row CSV into raw_data every ``--interval`` seconds. Everything else
(ingestion DAG -> Great Expectations -> ingestion_stats -> prediction DAG -> predictions) is the
normal pipeline, so every graph point on the dashboards comes from a genuine run.

Scenario (share of the run):  normal 40 % -> bad-data burst 15 % -> normal 10 % -> data drift 35 %
  * normal      : ~85 % clean files, 10 % mixed, 5 % all-errors
  * bad burst   : many all-errors / missing-column files  (data-quality dashboard + alerts)
  * drift       : valid but shifted files                 (drift dashboard + alerts)
Start it a few hours (or days, with a long --duration-min) before the defense.
"""
import argparse
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd

try:  # imported as a package (pytest)
    from scripts import generate_demo_data as gen
except ModuleNotFoundError:  # run directly
    import generate_demo_data as gen

PHASES = [  # (name, end of phase as a fraction of the run, {kind: probability})
    ("normal", 0.40, {"clean": 0.85, "mixed": 0.10, "all_errors": 0.05}),
    ("bad-data burst", 0.55, {"all_errors": 0.40, "missing_column": 0.25, "mixed": 0.20, "clean": 0.15}),
    ("normal", 0.65, {"clean": 0.85, "mixed": 0.10, "all_errors": 0.05}),
    ("drift", 1.01, {"drift": 0.85, "clean": 0.15}),
]


def phase_at(fraction: float):
    for name, end, probabilities in PHASES:
        if fraction < end:
            return name, probabilities
    return PHASES[-1][0], PHASES[-1][2]


def pick_kind(probabilities: dict, rng: np.random.Generator) -> str:
    kinds = list(probabilities)
    return str(rng.choice(kinds, p=np.array(list(probabilities.values())) / sum(probabilities.values())))


def build_file(kind: str, features: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """One 10-row file of the requested kind (features is the label-free clean pool)."""
    chunk = features.sample(n=gen.ROWS_PER_FILE, random_state=int(rng.integers(1_000_000))).reset_index(drop=True)
    if kind == "mixed":
        return gen.make_mixed(chunk)
    if kind == "all_errors":
        return gen.make_all_errors(chunk)
    if kind == "missing_column":
        return gen.make_missing_column(chunk)
    if kind == "drift":
        return gen.make_drifted(chunk, rng)
    return chunk


def main():
    parser = argparse.ArgumentParser(description="Drop realistic files into raw_data over time.")
    parser.add_argument("--input", required=True, help="Clean labelled dataset (label/id are dropped)")
    parser.add_argument("--raw-dir", default="data/raw_data")
    parser.add_argument("--interval", type=float, default=60, help="Seconds between two files")
    parser.add_argument("--duration-min", type=float, default=240, help="Total run time in minutes")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    features = pd.read_csv(args.input).drop(columns=["stroke", "id"], errors="ignore")
    rng = np.random.default_rng(args.seed)
    os.makedirs(args.raw_dir, exist_ok=True)
    total = max(1, int(args.duration_min * 60 / args.interval))
    print(f"Writing {total} files, one every {args.interval:.0f}s, into {args.raw_dir} (Ctrl+C to stop)")
    for i in range(total):
        phase, probabilities = phase_at(i / total)
        kind = pick_kind(probabilities, rng)
        name = f"sim_{datetime.now():%Y%m%d_%H%M%S}_{i:04d}_{kind}.csv"
        build_file(kind, features, rng).to_csv(os.path.join(args.raw_dir, name), index=False)
        print(f"[{i + 1}/{total}] phase={phase:14s} -> {name}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
