from typing import List, Tuple

import joblib
import pandas as pd

from app.schemas import Features

# Training-time column names (see model_training/train_model.ipynb) differ in
# casing from the API's snake_case field names for one column.
_FEATURE_RENAME = {"residence_type": "Residence_type"}


def load_model(model_path: str):
    return joblib.load(model_path)


def predict_batch(model, features: List[Features]) -> Tuple[List[int], List[float]]:
    rows = [f.model_dump() for f in features]
    df = pd.DataFrame(rows).rename(columns=_FEATURE_RENAME)
    df = df[list(model.feature_names_in_)]

    predictions = model.predict(df)
    probabilities = model.predict_proba(df)[:, 1]
    return predictions.tolist(), probabilities.tolist()
