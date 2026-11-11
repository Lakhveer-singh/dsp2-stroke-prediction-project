"""Regenerate the bundled fallback model (model_pipeline.pkl) with the shared training code.

The API serves the MLflow champion; this pickle is only the fallback used when the registry
has no champion / is unreachable. It must be trained with the SAME library versions as the
model_service image (see team5_service_web/model_service/requirements.txt), e.g.:

    pip install -r ../../team1_airflow/requirements.txt   # pandas 2.1.4, numpy 1.26.4, sklearn 1.7.2
    python export_fallback_model.py
"""
import os
import sys

import joblib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "team1_airflow", "dags"))
from common import training_helpers  # noqa: E402

REFERENCE = os.path.join(ROOT, "healthcare-dataset-stroke-data.xls")
OUTPUTS = [
    os.path.join(HERE, "artifacts", "model_pipeline.pkl"),
    os.path.join(os.path.dirname(ROOT), "team5_service_web", "model_service", "app", "artifacts", "model_pipeline.pkl"),
]


def main() -> None:
    datasets = training_helpers.build_datasets(REFERENCE, good_dir="", files=None)
    pipeline = training_helpers.train_pipeline(datasets["train"])
    print("test metrics:", training_helpers.evaluate_model(pipeline, datasets["test"]))
    for path in OUTPUTS:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(pipeline, path)
        print("wrote", path)


if __name__ == "__main__":
    main()
