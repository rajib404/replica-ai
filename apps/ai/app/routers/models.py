from fastapi import APIRouter, HTTPException, status

from app.models.models import (
    ModelCreateRequest,
    ModelCreateResponse,
    ModelInfoResponse,
    ModelPullRequest,
    ModelStatus,
)
from app.services.llm_engine import ModelManager, OllamaClient

router = APIRouter()

_ollama = OllamaClient()
_manager = ModelManager(client=_ollama)


@router.get("/models")
async def list_models() -> ModelStatus:
    """List available Ollama models."""
    health = await _ollama.health_check()

    models: list[dict] = []
    if health["status"] == "ok":
        try:
            models = await _ollama.list_models()
        except Exception:
            pass

    return ModelStatus(
        ollama_status=health["status"],
        ollama_detail=health.get("ollama_response") or health.get("error"),
        models=models,
    )


@router.post("/models/pull")
async def pull_model(body: ModelPullRequest) -> dict:
    """Pull a model from Ollama registry."""
    try:
        progress: list[dict] = []
        async for update in _ollama.pull_model(body.model):
            progress.append(update)
        return {"model": body.model, "progress": progress}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to pull model: {e}",
        ) from e


@router.post("/models/create", response_model=ModelCreateResponse)
async def create_model(body: ModelCreateRequest) -> ModelCreateResponse:
    """Create an owner-specific model from owner info."""
    try:
        result = await _manager.create_owner_model(
            owner_id=body.owner_id,
            owner_name=body.owner_name,
            language=body.language,
            additions=body.additions,
            base_model=body.base_model,
        )
        return ModelCreateResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create model: {e}",
        ) from e


@router.get("/models/{name}", response_model=ModelInfoResponse)
async def get_model(name: str) -> ModelInfoResponse:
    """Get details about a specific model."""
    try:
        info = await _ollama.show_model(name)
        return ModelInfoResponse(
            model_name=name,
            exists=True,
            details=info,
        )
    except Exception:
        return ModelInfoResponse(model_name=name, exists=False)
