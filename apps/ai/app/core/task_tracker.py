import enum
import json
import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

PREFIX = "knowledge:task:"
TTL_PENDING = 86400  # 24 hours
TTL_COMPLETED = 3600  # 1 hour


class TaskStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


async def create_task(r: aioredis.Redis, task_id: str, owner_id: str) -> dict:
    """Create a new background task entry in Redis."""
    now = datetime.now(UTC).isoformat()
    task = {
        "task_id": task_id,
        "owner_id": owner_id,
        "status": TaskStatus.pending.value,
        "progress": 0,
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    await r.setex(f"{PREFIX}{task_id}", TTL_PENDING, json.dumps(task))
    return task


async def update_task(
    r: aioredis.Redis,
    task_id: str,
    status: TaskStatus | None = None,
    progress: int | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Update fields on an existing task."""
    key = f"{PREFIX}{task_id}"
    raw = await r.get(key)
    if raw is None:
        return

    task = json.loads(raw)
    if status is not None:
        task["status"] = status.value
    if progress is not None:
        task["progress"] = progress
    if result is not None:
        task["result"] = result
    if error is not None:
        task["error"] = error
    task["updated_at"] = datetime.now(UTC).isoformat()

    ttl = TTL_COMPLETED if status in (TaskStatus.completed, TaskStatus.failed) else TTL_PENDING
    await r.setex(key, ttl, json.dumps(task))


async def get_task(r: aioredis.Redis, task_id: str) -> dict | None:
    """Retrieve a task by ID, or None if expired/missing."""
    raw = await r.get(f"{PREFIX}{task_id}")
    if raw is None:
        return None
    return json.loads(raw)
