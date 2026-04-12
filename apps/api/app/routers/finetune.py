"""Fine-tuning router: training data generation, jobs, versions, evaluation, rollback."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.database import async_session, get_db
from app.models.finetune import (
    EvaluateRequest,
    EvaluationResult,
    FineTuneConfigBody,
    FineTuneConfigResponse,
    FineTuneJob,
    FineTuneStartRequest,
    FineTuneStatusResponse,
    GenerateDataRequest,
    GenerateDataResponse,
    ModelVersionInfo,
    ModelVersionsResponse,
    RollbackRequest,
    RollbackResponse,
)
from app.models.owner import ModelVersion
from app.services.fine_tuner import FineTuner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/finetune", tags=["finetune"])


def _to_job(version: ModelVersion) -> FineTuneJob:
    return FineTuneJob(
        version_id=version.id,
        owner_id=version.owner_id,
        version=version.version,
        model_name=version.model_name,
        base_model=version.base_model,
        status=version.status,
        training_pair_count=version.training_pair_count,
        training_data_path=version.training_data_path,
        progress=version.progress,
        metrics=version.metrics,
        is_active=version.is_active,
        error_message=version.error_message,
        started_at=version.started_at.isoformat(),
        completed_at=version.completed_at.isoformat() if version.completed_at else None,
    )


def _to_version_info(version: ModelVersion) -> ModelVersionInfo:
    return ModelVersionInfo(
        version_id=version.id,
        version=version.version,
        model_name=version.model_name,
        base_model=version.base_model,
        status=version.status,
        is_active=version.is_active,
        training_pair_count=version.training_pair_count,
        metrics=version.metrics,
        started_at=version.started_at.isoformat(),
        completed_at=version.completed_at.isoformat() if version.completed_at else None,
    )


# ─── Training data ──────────────────────────────────────


@router.post("/generate-data", response_model=GenerateDataResponse)
async def generate_training_data(
    body: GenerateDataRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> GenerateDataResponse:
    """Build training pairs from the owner's conversations, knowledge, and personality."""
    try:
        stats, path, _ = await FineTuner.generate_training_data(
            auth.subject_id, db, save_to_disk=body.save_to_disk
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    warnings: list[str] = []
    if not stats.sufficient:
        warnings.append(
            f"Only {stats.total_pairs} pairs generated; "
            f"{stats.minimum_recommended} recommended for meaningful fine-tuning."
        )
    if stats.sources.conversation_pairs == 0:
        warnings.append("No conversation pairs found — chat with your replica more.")
    if stats.sources.knowledge_pairs == 0:
        warnings.append("No knowledge pairs generated — add knowledge entries first.")

    return GenerateDataResponse(stats=stats, training_file_path=path, warnings=warnings)


# ─── Start fine-tune job ────────────────────────────────


async def _run_fine_tune_job(owner_id: str, base_model: str | None) -> None:
    """Background coroutine that creates the model version end-to-end."""
    try:
        async with async_session() as db:
            await FineTuner.create_fine_tuned_model(
                owner_id, db, base_model=base_model
            )
    except Exception:
        logger.exception("Background fine-tune failed for owner %s", owner_id)


@router.post("/start", response_model=FineTuneJob)
async def start_fine_tune(
    body: FineTuneStartRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> FineTuneJob:
    """Kick off a fine-tune job for the authenticated owner.

    The job runs in the background; poll `/status` for progress.
    """
    running = await FineTuner.get_running_job(auth.subject_id, db)
    if running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A fine-tune job is already in progress (version {running.version}).",
        )

    # Validate that we have *some* training data before scheduling
    stats, _, _ = await FineTuner.generate_training_data(
        auth.subject_id, db, save_to_disk=False
    )
    if stats.total_pairs == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No training data available. Chat with your replica or add knowledge entries first.",
        )

    # Schedule the background job
    asyncio.create_task(_run_fine_tune_job(auth.subject_id, body.base_model))

    # Return a placeholder representation of the upcoming job
    config = await FineTuner.get_config(auth.subject_id, db)
    placeholder = FineTuneJob(
        version_id="pending",
        owner_id=auth.subject_id,
        version=0,
        model_name="pending",
        base_model=body.base_model or config.base_model,
        status="pending",
        training_pair_count=stats.total_pairs,
        training_data_path=None,
        progress={"stage": "queued"},
        metrics=None,
        is_active=False,
        error_message=None,
        started_at=stats.generated_at or "",
        completed_at=None,
    )
    return placeholder


# ─── Job status ─────────────────────────────────────────


@router.get("/status", response_model=FineTuneStatusResponse)
async def fine_tune_status(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> FineTuneStatusResponse:
    """Get the current and last fine-tune job status."""
    running = await FineTuner.get_running_job(auth.subject_id, db)
    last_completed = await FineTuner.get_last_completed(auth.subject_id, db)
    return FineTuneStatusResponse(
        current_job=_to_job(running) if running else None,
        queued=running is not None,
        last_completed=_to_job(last_completed) if last_completed else None,
    )


# ─── Versions ───────────────────────────────────────────


@router.get("/versions", response_model=ModelVersionsResponse)
async def list_model_versions(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ModelVersionsResponse:
    """List all stored model versions for the authenticated owner."""
    versions = await FineTuner.list_versions(auth.subject_id, db)
    active_version = next((v.version for v in versions if v.is_active), None)
    return ModelVersionsResponse(
        versions=[_to_version_info(v) for v in versions],
        active_version=active_version,
        total=len(versions),
    )


# ─── Evaluation ─────────────────────────────────────────


@router.post("/evaluate", response_model=EvaluationResult)
async def evaluate_model(
    body: EvaluateRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> EvaluationResult:
    """Run held-out evaluation comparing the fine-tuned model to its base."""
    try:
        return await FineTuner.evaluate_model(
            auth.subject_id, db, version=body.version
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ─── Rollback ───────────────────────────────────────────


@router.post("/rollback", response_model=RollbackResponse)
async def rollback_model(
    body: RollbackRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> RollbackResponse:
    """Restore a previous fine-tuned model version as the active one."""
    success, new_version, message = await FineTuner.rollback(
        auth.subject_id, db, version=body.version
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    return RollbackResponse(
        success=True, new_active_version=new_version, message=message
    )


# ─── Configuration ──────────────────────────────────────


@router.get("/config", response_model=FineTuneConfigResponse)
async def get_finetune_config(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> FineTuneConfigResponse:
    """Get fine-tuning preferences for the owner."""
    config = await FineTuner.get_config(auth.subject_id, db)
    total_messages = await FineTuner.count_owner_messages(auth.subject_id, db)
    pending = max(0, config.trigger_message_count - (total_messages - config.last_trigger_message_total))
    return FineTuneConfigResponse(
        owner_id=config.owner_id,
        auto_approve=config.auto_approve,
        auto_trigger_enabled=config.auto_trigger_enabled,
        base_model=config.base_model,
        trigger_message_count=config.trigger_message_count,
        last_trigger_message_total=config.last_trigger_message_total,
        current_owner_message_count=total_messages,
        pending_messages_until_trigger=pending,
    )


@router.put("/config", response_model=FineTuneConfigResponse)
async def update_finetune_config(
    body: FineTuneConfigBody,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> FineTuneConfigResponse:
    """Update fine-tuning preferences for the owner."""
    config = await FineTuner.upsert_config(
        auth.subject_id,
        db,
        auto_approve=body.auto_approve,
        auto_trigger_enabled=body.auto_trigger_enabled,
        base_model=body.base_model,
        trigger_message_count=body.trigger_message_count,
    )
    total_messages = await FineTuner.count_owner_messages(auth.subject_id, db)
    pending = max(0, config.trigger_message_count - (total_messages - config.last_trigger_message_total))
    return FineTuneConfigResponse(
        owner_id=config.owner_id,
        auto_approve=config.auto_approve,
        auto_trigger_enabled=config.auto_trigger_enabled,
        base_model=config.base_model,
        trigger_message_count=config.trigger_message_count,
        last_trigger_message_total=config.last_trigger_message_total,
        current_owner_message_count=total_messages,
        pending_messages_until_trigger=pending,
    )
