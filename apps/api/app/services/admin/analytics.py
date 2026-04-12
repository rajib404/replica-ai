"""Analytics queries for the admin dashboard.

All queries run against existing tables — no new state is introduced.
Time series are computed in PostgreSQL via `date_trunc('day', col)` and
returned as a list of `{date, value}` dicts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ConversationThread, Message
from app.models.knowledge import KnowledgeEntry
from app.models.owner import ExternalLLMUsageLog


def _date_str(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _start(days: int) -> datetime:
    return (datetime.now(UTC) - timedelta(days=days)).replace(tzinfo=None)


async def daily_active_users(db: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    start = _start(days)
    day = func.date_trunc("day", Message.created_at).label("day")
    rows = (
        await db.execute(
            select(day, func.count(distinct(ConversationThread.owner_id)))
            .join(ConversationThread, ConversationThread.id == Message.thread_id)
            .where(Message.created_at >= start)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return [{"date": _date_str(r[0]), "value": int(r[1])} for r in rows]


async def message_volume(db: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    start = _start(days)
    day = func.date_trunc("day", Message.created_at).label("day")
    rows = (
        await db.execute(
            select(day, func.count(Message.id))
            .where(Message.created_at >= start)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return [{"date": _date_str(r[0]), "value": int(r[1])} for r in rows]


async def knowledge_ingestion_rate(db: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    start = _start(days)
    day = func.date_trunc("day", KnowledgeEntry.created_at).label("day")
    rows = (
        await db.execute(
            select(day, func.count(KnowledgeEntry.id))
            .where(KnowledgeEntry.created_at >= start)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return [{"date": _date_str(r[0]), "value": int(r[1])} for r in rows]


async def knowledge_type_distribution(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(KnowledgeEntry.content_type, func.count(KnowledgeEntry.id))
            .group_by(KnowledgeEntry.content_type)
        )
    ).all()
    return [
        {
            "content_type": (
                r[0].value if hasattr(r[0], "value") else str(r[0])
            ),
            "count": int(r[1]),
        }
        for r in rows
    ]


async def external_llm_usage(db: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    start = _start(days)
    day = func.date_trunc("day", ExternalLLMUsageLog.created_at).label("day")
    rows = (
        await db.execute(
            select(
                day,
                ExternalLLMUsageLog.provider,
                func.coalesce(func.sum(ExternalLLMUsageLog.cost_usd), 0.0),
                func.coalesce(
                    func.sum(
                        ExternalLLMUsageLog.prompt_tokens
                        + ExternalLLMUsageLog.completion_tokens
                    ),
                    0,
                ),
            )
            .where(ExternalLLMUsageLog.created_at >= start)
            .group_by(day, ExternalLLMUsageLog.provider)
            .order_by(day)
        )
    ).all()
    return [
        {
            "date": _date_str(r[0]),
            "provider": r[1].value if hasattr(r[1], "value") else str(r[1]),
            "cost_usd": float(r[2]),
            "tokens": int(r[3]),
        }
        for r in rows
    ]


def _linear_regression(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Hand-rolled least-squares fit. Returns ``(slope, intercept)``."""
    n = len(points)
    if n == 0:
        return 0.0, 0.0
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xx = sum(p[0] * p[0] for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0.0, sum_y / n
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


async def storage_growth_projection(
    db: AsyncSession, days: int = 30, project_days: int = 90
) -> list[dict[str, Any]]:
    """Daily knowledge counts for the past `days`, plus a linear projection."""
    start = _start(days)
    day = func.date_trunc("day", KnowledgeEntry.created_at).label("day")
    rows = (
        await db.execute(
            select(day, func.count(KnowledgeEntry.id))
            .where(KnowledgeEntry.created_at >= start)
            .group_by(day)
            .order_by(day)
        )
    ).all()

    cumulative = 0
    history: list[dict[str, Any]] = []
    points_for_fit: list[tuple[float, float]] = []
    for idx, row in enumerate(rows):
        cumulative += int(row[1])
        history.append({"date": _date_str(row[0]), "value": float(cumulative), "projected": False})
        points_for_fit.append((float(idx), float(cumulative)))

    if not history:
        return []

    slope, intercept = _linear_regression(points_for_fit)
    last_date = (
        datetime.fromisoformat(history[-1]["date"]) if history else datetime.now(UTC)
    )
    base_index = len(points_for_fit) - 1

    projected: list[dict[str, Any]] = []
    for offset in range(1, project_days + 1):
        x = float(base_index + offset)
        value = max(0.0, slope * x + intercept)
        projected.append(
            {
                "date": (last_date + timedelta(days=offset)).date().isoformat(),
                "value": value,
                "projected": True,
            }
        )
    return history + projected
