"""System overview + resource statistics."""

from __future__ import annotations

import os
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ConversationThread, Message
from app.models.knowledge import KnowledgeEntry
from app.models.owner import InstanceStatus, ModelInstance, Owner

# Module-level boot time so we can report uptime in /overview.
_BOOT_TIME = time.time()


def _maybe_psutil() -> Any | None:  # pragma: no cover - import shim
    try:
        import psutil  # type: ignore[import-not-found]

        return psutil
    except ImportError:
        return None


def get_system_resources() -> dict[str, Any]:
    """Snapshot CPU/memory/disk for the host process.

    If `psutil` isn't installed we return zeros so the endpoint stays
    callable in test environments.
    """
    psutil = _maybe_psutil()
    if psutil is None:
        return {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_used_bytes": 0,
            "memory_total_bytes": 0,
            "disk_percent": 0.0,
            "disk_used_bytes": 0,
            "disk_total_bytes": 0,
        }

    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(os.getcwd())
    return {
        "cpu_percent": float(psutil.cpu_percent(interval=None)),
        "memory_percent": float(vm.percent),
        "memory_used_bytes": int(vm.used),
        "memory_total_bytes": int(vm.total),
        "disk_percent": float(disk.percent),
        "disk_used_bytes": int(disk.used),
        "disk_total_bytes": int(disk.total),
    }


async def get_system_overview(db: AsyncSession) -> dict[str, Any]:
    """Aggregate counts and resource stats for the admin overview page."""
    owner_count = (await db.execute(select(func.count(Owner.id)))).scalar_one()
    knowledge_count = (
        await db.execute(select(func.count(KnowledgeEntry.id)))
    ).scalar_one()
    active_instance_count = (
        await db.execute(
            select(func.count(ModelInstance.id)).where(
                ModelInstance.status == InstanceStatus.active
            )
        )
    ).scalar_one()
    message_count = (await db.execute(select(func.count(Message.id)))).scalar_one()
    thread_count = (
        await db.execute(select(func.count(ConversationThread.id)))
    ).scalar_one()

    # Best-effort storage estimate: sum of message + knowledge text byte length.
    storage_messages = (
        await db.execute(
            select(func.coalesce(func.sum(func.length(Message.content_text)), 0))
        )
    ).scalar_one()
    storage_knowledge = (
        await db.execute(
            select(
                func.coalesce(func.sum(func.length(KnowledgeEntry.english_translation)), 0)
            )
        )
    ).scalar_one()

    return {
        "owner_count": int(owner_count),
        "knowledge_count": int(knowledge_count),
        "active_instance_count": int(active_instance_count),
        "message_count": int(message_count),
        "thread_count": int(thread_count),
        "approximate_storage_bytes": int(storage_messages) + int(storage_knowledge),
        "resources": get_system_resources(),
        "uptime_seconds": time.time() - _BOOT_TIME,
    }
