"""External LLM gateway endpoints: query, config CRUD, usage."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.models.external_llm import (
    BudgetAlertResponse,
    CreateExternalLLMConfigRequest,
    ExternalLLMConfigListResponse,
    ExternalLLMConfigResponse,
    ExternalQueryRequest,
    ExternalQueryResponse,
    UpdateExternalLLMConfigRequest,
    UsageLogEntry,
    UsageSummary,
)
from app.services.external_llm import ExternalLLMGateway

router = APIRouter(prefix="/api/external", tags=["external-llm"])


def _config_to_response(c) -> ExternalLLMConfigResponse:  # noqa: ANN001
    return ExternalLLMConfigResponse(
        id=c.id,
        owner_id=c.owner_id,
        provider=c.provider.value,
        model_name=c.model_name,
        monthly_budget_usd=c.monthly_budget_usd,
        daily_budget_usd=c.daily_budget_usd,
        spent_this_month_usd=c.spent_this_month_usd,
        is_active=c.is_active,
        auto_learn=c.auto_learn,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


# ─── Config CRUD ─────────────────────────────────────────


@router.post("/config", status_code=201, response_model=ExternalLLMConfigResponse)
async def create_config(
    body: CreateExternalLLMConfigRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ExternalLLMConfigResponse:
    config = await ExternalLLMGateway.create_config(
        owner_id=auth.subject_id,
        provider=body.provider,
        api_key=body.api_key,
        model_name=body.model_name,
        monthly_budget_usd=body.monthly_budget_usd,
        daily_budget_usd=body.daily_budget_usd,
        auto_learn=body.auto_learn,
        db=db,
    )
    return _config_to_response(config)


@router.get("/config", response_model=ExternalLLMConfigListResponse)
async def list_configs(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ExternalLLMConfigListResponse:
    configs = await ExternalLLMGateway.get_configs(auth.subject_id, db)
    return ExternalLLMConfigListResponse(
        configs=[_config_to_response(c) for c in configs],
        total=len(configs),
    )


@router.get("/config/{config_id}", response_model=ExternalLLMConfigResponse)
async def get_config(
    config_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ExternalLLMConfigResponse:
    config = await ExternalLLMGateway.get_config(config_id, auth.subject_id, db)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found.")
    return _config_to_response(config)


@router.put("/config/{config_id}", response_model=ExternalLLMConfigResponse)
async def update_config(
    config_id: str,
    body: UpdateExternalLLMConfigRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ExternalLLMConfigResponse:
    config = await ExternalLLMGateway.get_config(config_id, auth.subject_id, db)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found.")
    updates = body.model_dump(exclude_none=True)
    config = await ExternalLLMGateway.update_config(config, updates, db)
    return _config_to_response(config)


@router.delete("/config/{config_id}", status_code=204)
async def delete_config(
    config_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await ExternalLLMGateway.delete_config(config_id, auth.subject_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Config not found.")


# ─── Query ───────────────────────────────────────────────


@router.post("/query", response_model=ExternalQueryResponse)
async def query_external(
    body: ExternalQueryRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ExternalQueryResponse:
    try:
        result = await ExternalLLMGateway.query_external(
            owner_id=auth.subject_id,
            prompt=body.prompt,
            db=db,
            config_id=body.config_id,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            learn=body.learn,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ExternalQueryResponse(**result)


# ─── Usage ───────────────────────────────────────────────


@router.get("/usage", response_model=UsageSummary)
async def get_usage(
    config_id: str | None = None,
    limit: int = 50,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> UsageSummary:
    data = await ExternalLLMGateway.get_usage(
        auth.subject_id, db, config_id=config_id, limit=limit
    )
    return UsageSummary(
        total_cost_usd=data["total_cost_usd"],
        total_queries=data["total_queries"],
        total_prompt_tokens=data["total_prompt_tokens"],
        total_completion_tokens=data["total_completion_tokens"],
        budget_remaining_monthly=data["budget_remaining_monthly"],
        budget_pct_used=data["budget_pct_used"],
        logs=[
            UsageLogEntry(
                id=log.id,
                provider=log.provider.value,
                prompt_tokens=log.prompt_tokens,
                completion_tokens=log.completion_tokens,
                cost_usd=log.cost_usd,
                was_sanitized=log.was_sanitized,
                created_at=log.created_at,
            )
            for log in data["logs"]
        ],
    )


@router.get("/budget", response_model=BudgetAlertResponse)
async def get_budget_status(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> BudgetAlertResponse:
    configs = await ExternalLLMGateway.get_configs(auth.subject_id, db)
    total_budget = sum(c.monthly_budget_usd for c in configs)
    total_spent = sum(c.spent_this_month_usd for c in configs)
    pct = (total_spent / total_budget * 100) if total_budget > 0 else 0.0
    alert = pct >= settings.external_llm_budget_alert_pct * 100

    if pct >= 100:
        message = "Monthly budget exhausted. External queries are disabled."
    elif alert:
        message = f"Budget warning: {pct:.0f}% of monthly budget used."
    else:
        message = f"Budget healthy: {pct:.0f}% used."

    return BudgetAlertResponse(
        alert=alert,
        pct_used=round(pct, 1),
        monthly_budget_usd=total_budget,
        spent_this_month_usd=round(total_spent, 4),
        message=message,
    )
