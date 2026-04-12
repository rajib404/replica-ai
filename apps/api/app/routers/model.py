import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_auth
from app.core.database import async_session, get_db
from app.models.llm import (
    ModelInfoResponse,
    ModelInitializeRequest,
    ModelInitializeResponse,
    ModelStatusResponse,
    ModelSwitchRequest,
    ModelSwitchResponse,
)
from app.models.owner import ModelVersion, Owner
from app.services.fine_tuner import FineTuner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/model", tags=["model"])


@router.get("/status", response_model=ModelStatusResponse)
async def model_status(
    ai: AIServiceClient = Depends(get_ai_client),
) -> ModelStatusResponse:
    """Ollama health check and list of loaded models (proxied to AI service)."""
    try:
        data = await ai.list_models()
        return ModelStatusResponse(
            ollama_status=data.get("ollama_status", "unknown"),
            ollama_detail=data.get("ollama_detail"),
            models=data.get("models", []),
        )
    except Exception:
        return ModelStatusResponse(ollama_status="unreachable")


@router.post(
    "/initialize",
    response_model=ModelInitializeResponse,
    dependencies=[Depends(require_auth)],
)
async def model_initialize(
    request: ModelInitializeRequest,
    auth: AuthContext = Depends(require_auth),
    ai: AIServiceClient = Depends(get_ai_client),
    db: AsyncSession = Depends(get_db),
) -> ModelInitializeResponse:
    """Pull the base model (if needed) and create the owner's custom model."""
    if auth.role != "owner" or auth.subject_id != request.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only initialize your own model",
        )

    # Fetch owner info from DB to pass to AI service
    result = await db.execute(select(Owner).where(Owner.id == request.owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Owner {request.owner_id} not found"
        )

    try:
        # Ensure base model is pulled
        await ai.pull_model(request.model or "mistral:7b-instruct")
        base_status = "ready"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to pull base model: {e}",
        ) from e

    try:
        owner_model = await ai.create_model(
            owner_id=request.owner_id,
            owner_name=owner.name,
            language=owner.preferred_language,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create owner model: {e}",
        ) from e

    return ModelInitializeResponse(
        base_model_status=base_status,
        owner_model=owner_model,
    )


@router.get(
    "/info",
    response_model=ModelInfoResponse,
    dependencies=[Depends(require_auth)],
)
async def model_info(
    auth: AuthContext = Depends(require_auth),
    ai: AIServiceClient = Depends(get_ai_client),
) -> ModelInfoResponse:
    """Get current model details for the authenticated owner."""
    model_name = f"replica-{auth.subject_id[:12]}"
    try:
        data = await ai.get_model(model_name)
        if not data.get("exists", False):
            return ModelInfoResponse(exists=False)
        return ModelInfoResponse(
            model_name=data.get("model_name"),
            exists=True,
            details=data.get("details"),
        )
    except Exception:
        return ModelInfoResponse(exists=False)


@router.post(
    "/switch",
    response_model=ModelSwitchResponse,
    dependencies=[Depends(require_auth)],
)
async def model_switch(
    request: ModelSwitchRequest,
    auth: AuthContext = Depends(require_auth),
    ai: AIServiceClient = Depends(get_ai_client),
    db: AsyncSession = Depends(get_db),
) -> ModelSwitchResponse:
    """Switch the owner's base LLM and re-train if training data exists."""
    if auth.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can switch models",
        )

    owner_id = auth.subject_id
    new_base = request.new_base_model

    # Fetch owner
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owner {owner_id} not found",
        )

    # Get or create fine-tune config
    config = await FineTuner.get_config(owner_id, db)

    # Idempotency: already on this base model
    if config.base_model == new_base:
        return ModelSwitchResponse(
            status="no_change",
            previous_base_model=config.base_model,
            new_base_model=new_base,
            message="Already using this base model",
        )

    # Conflict: check for running fine-tune job
    running = await FineTuner.get_running_job(owner_id, db)
    if running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A fine-tuning job is already in progress. Wait for it to complete before switching models.",
        )

    previous_base = config.base_model

    # Update config with new base model
    config.base_model = new_base
    await db.commit()

    # Deactivate all active ModelVersion rows for this owner
    active_rows = await db.execute(
        select(ModelVersion).where(
            ModelVersion.owner_id == owner_id,
            ModelVersion.is_active.is_(True),
        )
    )
    for mv in active_rows.scalars().all():
        mv.is_active = False
    await db.commit()

    # Check if last completed version has training data
    last_completed = await FineTuner.get_last_completed(owner_id, db)
    has_training_data = (
        last_completed is not None and last_completed.training_pair_count > 0
    )

    # Launch background task
    asyncio.create_task(
        _run_model_switch(
            owner_id=owner_id,
            owner_name=owner.name,
            language=owner.preferred_language,
            new_base=new_base,
            retrain=has_training_data,
        )
    )

    return ModelSwitchResponse(
        status="switching",
        previous_base_model=previous_base,
        new_base_model=new_base,
        model_pull_started=True,
        retrain_triggered=has_training_data,
        message=(
            f"Switching from {previous_base} to {new_base}. "
            + ("Re-training will start after model pull." if has_training_data else "No training data to re-train.")
        ),
    )


async def _run_model_switch(
    *,
    owner_id: str,
    owner_name: str,
    language: str,
    new_base: str,
    retrain: bool,
) -> None:
    """Background job: pull new base model, recreate owner model, optionally re-train."""
    from app.core.ai_client import get_ai_client

    ai = get_ai_client()

    try:
        # 1. Pull the new base model from Ollama registry
        logger.info("Model switch: pulling %s for owner %s", new_base, owner_id)
        await ai.pull_model(new_base)
    except Exception:
        logger.exception("Model switch: failed to pull %s", new_base)
        return

    try:
        # 2. Recreate the base owner model with new base
        logger.info("Model switch: creating owner model with base %s", new_base)
        await ai.create_model(
            owner_id=owner_id,
            owner_name=owner_name,
            language=language,
            base_model=new_base,
        )
    except Exception:
        logger.exception("Model switch: failed to create owner model with %s", new_base)
        return

    # 3. Re-train if training data exists
    if retrain:
        try:
            logger.info("Model switch: re-training owner %s with base %s", owner_id, new_base)
            async with async_session() as db:
                await FineTuner.create_fine_tuned_model(
                    owner_id, db, base_model=new_base
                )
            logger.info("Model switch: re-training complete for owner %s", owner_id)
        except Exception:
            logger.exception("Model switch: re-training failed for owner %s", owner_id)
