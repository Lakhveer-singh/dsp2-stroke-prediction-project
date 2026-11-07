import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import MODEL_PATH
from app.database import Base, engine
from app.ml_model import load_model
from app.routers import health, past_predictions, predict


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    app.state.model = load_model(MODEL_PATH)
    app.state.model_version = os.path.basename(MODEL_PATH)
    yield


app = FastAPI(title="DSP Stroke Prediction Model Service", lifespan=lifespan)

app.include_router(health.router)
app.include_router(predict.router)
app.include_router(past_predictions.router)
