"""Knowledge entry CRUD operations (DB only).

AI ingestion is handled by the standalone AI service (apps/ai).
This module retains only PostgreSQL CRUD operations for knowledge entries.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import ContentType, KnowledgeEntry

logger = logging.getLogger(__name__)


async def list_entries(
    owner_id: str,
    db: AsyncSession,
    content_type: ContentType | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[KnowledgeEntry], int]:
    """Return paginated entries for an owner."""
    base_filter = KnowledgeEntry.owner_id == owner_id
    if content_type is not None:
        base_filter = base_filter & (KnowledgeEntry.content_type == content_type)

    total_result = await db.execute(
        select(func.count(KnowledgeEntry.id)).where(base_filter)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(KnowledgeEntry)
        .where(base_filter)
        .order_by(KnowledgeEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    entries = list(result.scalars().all())
    return entries, total


async def get_entry(
    entry_id: str, owner_id: str, db: AsyncSession
) -> KnowledgeEntry | None:
    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_entry(
    entry_id: str, owner_id: str, db: AsyncSession
) -> bool:
    entry = await get_entry(entry_id, owner_id, db)
    if entry is None:
        return False

    await db.delete(entry)
    await db.commit()
    return True
