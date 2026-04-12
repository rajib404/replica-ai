"""Admin SystemRule + SystemConfig CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import AdminContext, require_admin
from app.core.database import get_db
from app.models.admin import SystemRule
from app.models.admin_schemas import (
    SystemConfigResponse,
    SystemConfigUpdate,
    SystemRuleCreate,
    SystemRuleResponse,
    SystemRuleUpdate,
)
from app.services.admin import rules as rules_service

router = APIRouter()


def _serialize_rule(rule: SystemRule) -> SystemRuleResponse:
    return SystemRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        system_prompt=rule.system_prompt,
        personality_baseline=rule.personality_baseline,
        rate_limits=rule.rate_limits,
        file_size_limit_bytes=rule.file_size_limit_bytes,
        base_model=rule.base_model,
        is_default=rule.is_default,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/rules", response_model=list[SystemRuleResponse])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> list[SystemRuleResponse]:
    rules = await rules_service.list_rules(db)
    return [_serialize_rule(r) for r in rules]


@router.post("/rules", response_model=SystemRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: SystemRuleCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> SystemRuleResponse:
    rule = await rules_service.create_rule(db, payload)
    return _serialize_rule(rule)


@router.get("/rules/{rule_id}", response_model=SystemRuleResponse)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> SystemRuleResponse:
    rule = await rules_service.get_rule(db, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return _serialize_rule(rule)


@router.put("/rules/{rule_id}", response_model=SystemRuleResponse)
async def update_rule(
    rule_id: str,
    payload: SystemRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> SystemRuleResponse:
    rule = await rules_service.update_rule(db, rule_id, payload)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return _serialize_rule(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> None:
    try:
        deleted = await rules_service.delete_rule(db, rule_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")


@router.get("/config", response_model=SystemConfigResponse)
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> SystemConfigResponse:
    config = await rules_service.get_system_config(db)
    return SystemConfigResponse(
        id=config.id,
        default_rule_id=config.default_rule_id,
        default_base_model=config.default_base_model,
        global_rate_limit_per_minute=config.global_rate_limit_per_minute,
        global_file_size_limit_bytes=config.global_file_size_limit_bytes,
        maintenance_mode=config.maintenance_mode,
        updated_at=config.updated_at,
    )


@router.put("/config", response_model=SystemConfigResponse)
async def update_config(
    payload: SystemConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> SystemConfigResponse:
    config = await rules_service.update_system_config(db, payload)
    return SystemConfigResponse(
        id=config.id,
        default_rule_id=config.default_rule_id,
        default_base_model=config.default_base_model,
        global_rate_limit_per_minute=config.global_rate_limit_per_minute,
        global_file_size_limit_bytes=config.global_file_size_limit_bytes,
        maintenance_mode=config.maintenance_mode,
        updated_at=config.updated_at,
    )
