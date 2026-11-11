from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.model_registry import ModelHolder
from app.routers import health, past_predictions, predict, reload_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    holder = ModelHolder()
    holder.initialize()
    app.state.model_holder = holder
    yield


app = FastAPI(title="DSP Stroke Prediction Model Service", lifespan=lifespan)

app.include_router(health.router)
app.include_router(predict.router)
app.include_router(past_predictions.router)
app.include_router(reload_model.router)
