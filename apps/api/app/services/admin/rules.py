"""SystemRule + SystemConfig CRUD for the admin dashboard."""

from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import SystemConfig, SystemRule


def _new_id() -> str:
    return secrets.token_urlsafe(16)


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    return dict(payload)


async def list_rules(db: AsyncSession) -> list[SystemRule]:
    result = await db.execute(select(SystemRule).order_by(SystemRule.created_at.desc()))
    return list(result.scalars().all())


async def get_rule(db: AsyncSession, rule_id: str) -> SystemRule | None:
    return await db.scalar(select(SystemRule).where(SystemRule.id == rule_id))


async def _unset_other_defaults(db: AsyncSession, except_id: str | None) -> None:
    stmt = update(SystemRule).values(is_default=False).where(SystemRule.is_default.is_(True))
    if except_id is not None:
        stmt = stmt.where(SystemRule.id != except_id)
    await db.execute(stmt)


async def create_rule(db: AsyncSession, payload: Any) -> SystemRule:
    data = _payload_to_dict(payload)
    rate_limits = data.pop("rate_limits", None)
    if rate_limits is not None and hasattr(rate_limits, "model_dump"):
        rate_limits = rate_limits.model_dump(exclude_unset=True)
    rule = SystemRule(
        id=_new_id(),
        name=data["name"],
        description=data.get("description"),
        system_prompt=data.get("system_prompt"),
        personality_baseline=data.get("personality_baseline"),
        rate_limits=rate_limits,
        file_size_limit_bytes=data.get("file_size_limit_bytes"),
        base_model=data.get("base_model"),
        is_default=bool(data.get("is_default", False)),
    )
    if rule.is_default:
        await _unset_other_defaults(db, except_id=None)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_rule(db: AsyncSession, rule_id: str, payload: Any) -> SystemRule | None:
    rule = await get_rule(db, rule_id)
    if rule is None:
        return None
    data = _payload_to_dict(payload)
    rate_limits = data.pop("rate_limits", None)
    if rate_limits is not None and hasattr(rate_limits, "model_dump"):
        rate_limits = rate_limits.model_dump(exclude_unset=True)
    if rate_limits is not None:
        rule.rate_limits = rate_limits

    for field in (
        "name",
        "description",
        "system_prompt",
        "personality_baseline",
        "file_size_limit_bytes",
        "base_model",
    ):
        if field in data:
            setattr(rule, field, data[field])

    if "is_default" in data and data["is_default"] is not None:
        rule.is_default = bool(data["is_default"])
        if rule.is_default:
            await _unset_other_defaults(db, except_id=rule.id)

    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule_id: str) -> bool:
    rule = await get_rule(db, rule_id)
    if rule is None:
        return False
    if rule.is_default:
        # Refuse to leave the system without any default rule.
        other_default = await db.scalar(
            select(SystemRule).where(SystemRule.id != rule_id, SystemRule.is_default.is_(True))
        )
        if other_default is None:
            raise ValueError("Cannot delete the only default rule")
    await db.delete(rule)
    await db.commit()
    return True


async def get_system_config(db: AsyncSession) -> SystemConfig:
    config = await db.scalar(select(SystemConfig).where(SystemConfig.id == "singleton"))
    if config is None:
        config = SystemConfig(id="singleton")
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


async def update_system_config(db: AsyncSession, payload: Any) -> SystemConfig:
    config = await get_system_config(db)
    data = _payload_to_dict(payload)
    for field in (
        "default_rule_id",
        "default_base_model",
        "global_rate_limit_per_minute",
        "global_file_size_limit_bytes",
        "maintenance_mode",
    ):
        if field in data:
            setattr(config, field, data[field])
    await db.commit()
    await db.refresh(config)
    return config
