from fastapi import APIRouter, HTTPException, Request

from app.model_registry import NoChampionError, RegistryUnavailable
from app.schemas import ModelInfoResponse, ReloadModelResponse

router = APIRouter()


@router.post("/reload-model", response_model=ReloadModelResponse)
def reload_model(request: Request) -> ReloadModelResponse:
    """Load the model version currently aliased ``champion`` in the MLflow registry.

    Called by the training DAG after a successful promotion; no container restart needed.
    """
    holder = request.app.state.model_holder
    try:
        previous, current = holder.reload_from_registry()
    except NoChampionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RegistryUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"model registry unavailable: {exc}") from exc
    return ReloadModelResponse(status="reloaded", previous_model_version=previous, model_version=current)


@router.get("/model-info", response_model=ModelInfoResponse)
def model_info(request: Request) -> ModelInfoResponse:
    holder = request.app.state.model_holder
    return ModelInfoResponse(model_version=holder.version, origin=holder.origin)
