from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml_model import predict_batch
from app.models_orm import Prediction
from app.schemas import PredictRequest, PredictResponse, PredictionResult

router = APIRouter()


@router.post("/predict", response_model=PredictResponse, status_code=status.HTTP_200_OK)
def predict(payload: PredictRequest, request: Request, db: Session = Depends(get_db)) -> PredictResponse:
    if not payload.features:
        raise HTTPException(status_code=400, detail="features must not be empty")

    # model and version are read together under a lock so a concurrent /reload-model
    # can never produce a prediction labelled with the wrong version.
    model, model_version = request.app.state.model_holder.get()

    try:
        predictions, probabilities = predict_batch(model, payload.features)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"prediction failed: {exc}") from exc

    results = []
    for feature, prediction, probability in zip(payload.features, predictions, probabilities):
        db.add(
            Prediction(
                source=payload.source,
                model_version=model_version,
                gender=feature.gender,
                age=feature.age,
                hypertension=feature.hypertension,
                heart_disease=feature.heart_disease,
                ever_married=feature.ever_married,
                work_type=feature.work_type,
                residence_type=feature.residence_type,
                avg_glucose_level=feature.avg_glucose_level,
                bmi=feature.bmi,
                smoking_status=feature.smoking_status,
                prediction=int(prediction),
                prediction_proba=float(probability),
            )
        )
        results.append(
            PredictionResult(
                gender=feature.gender,
                age=feature.age,
                hypertension=feature.hypertension,
                heart_disease=feature.heart_disease,
                ever_married=feature.ever_married,
                work_type=feature.work_type,
                residence_type=feature.residence_type,
                avg_glucose_level=feature.avg_glucose_level,
                bmi=feature.bmi,
                smoking_status=feature.smoking_status,
                prediction=int(prediction),
                prediction_proba=float(probability),
            )
        )

    db.commit()
    return PredictResponse(model_version=model_version, results=results)
