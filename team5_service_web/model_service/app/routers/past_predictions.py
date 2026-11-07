from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_orm import Prediction
from app.schemas import PastPredictionRecord, PastPredictionsResponse

router = APIRouter()


@router.get("/past-predictions", response_model=PastPredictionsResponse)
def get_past_predictions(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    source: Literal["webapp", "scheduled", "all"] = Query(default="all"),
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
) -> PastPredictionsResponse:
    query = db.query(Prediction)

    if start_date is not None:
        query = query.filter(Prediction.prediction_time >= start_date)
    if end_date is not None:
        query = query.filter(Prediction.prediction_time < end_date + timedelta(days=1))
    if source != "all":
        query = query.filter(Prediction.source == source)

    rows = query.order_by(Prediction.prediction_time.desc()).limit(limit).all()
    results = [PastPredictionRecord.model_validate(row, from_attributes=True) for row in rows]
    return PastPredictionsResponse(count=len(results), results=results)
