from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Features(BaseModel):
    gender: Literal["Male", "Female", "Other"]
    age: float = Field(ge=0, le=120)
    hypertension: Literal[0, 1]
    heart_disease: Literal[0, 1]
    ever_married: Literal["Yes", "No"]
    work_type: Literal["Private", "Self-employed", "Govt_job", "children", "Never_worked"]
    residence_type: Literal["Urban", "Rural"]
    avg_glucose_level: float = Field(gt=0)
    bmi: Optional[float] = Field(default=None, gt=0)
    smoking_status: Literal["formerly smoked", "never smoked", "smokes", "Unknown"]


class PredictRequest(BaseModel):
    features: List[Features]
    source: Literal["webapp", "scheduled"]


class PredictionResult(BaseModel):
    gender: str
    age: float
    hypertension: int
    heart_disease: int
    ever_married: str
    work_type: str
    residence_type: str
    avg_glucose_level: float
    bmi: Optional[float]
    smoking_status: str
    prediction: int
    prediction_proba: float


class PredictResponse(BaseModel):
    model_version: str
    results: List[PredictionResult]


class PastPredictionRecord(PredictionResult):
    id: int
    prediction_time: datetime
    source: str
    model_version: str


class PastPredictionsResponse(BaseModel):
    count: int
    results: List[PastPredictionRecord]


class HealthResponse(BaseModel):
    status: Literal["healthy"]
