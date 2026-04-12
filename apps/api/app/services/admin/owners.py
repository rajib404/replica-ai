"""Admin owners listing + detail."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ConversationThread, Message
from app.models.knowledge import KnowledgeEntry
from app.models.owner import ModelInstance, Owner


async def list_owners(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    instance_count = (
        select(ModelInstance.owner_id, func.count(ModelInstance.id).label("c"))
        .group_by(ModelInstance.owner_id)
        .subquery()
    )
    knowledge_count = (
        select(KnowledgeEntry.owner_id, func.count(KnowledgeEntry.id).label("c"))
        .group_by(KnowledgeEntry.owner_id)
        .subquery()
    )
    message_count = (
        select(
            ConversationThread.owner_id.label("owner_id"),
            func.count(Message.id).label("c"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .join(Message, Message.thread_id == ConversationThread.id)
        .group_by(ConversationThread.owner_id)
        .subquery()
    )

    base = (
        select(
            Owner.id,
            Owner.name,
            Owner.email,
            Owner.created_at,
            Owner.updated_at,
            func.coalesce(instance_count.c.c, 0).label("instance_count"),
            func.coalesce(knowledge_count.c.c, 0).label("knowledge_count"),
            func.coalesce(message_count.c.c, 0).label("message_count"),
            case(
                (
                    message_count.c.last_message_at.is_(None),
                    Owner.updated_at,
                ),
                else_=func.greatest(message_count.c.last_message_at, Owner.updated_at),
            ).label("last_active_at"),
        )
        .select_from(Owner)
        .outerjoin(instance_count, instance_count.c.owner_id == Owner.id)
        .outerjoin(knowledge_count, knowledge_count.c.owner_id == Owner.id)
        .outerjoin(message_count, message_count.c.owner_id == Owner.id)
    )

    if search:
        like = f"%{search.lower()}%"
        base = base.where(
            or_(func.lower(Owner.name).like(like), func.lower(Owner.email).like(like))
        )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(
                case(
                    (
                        message_count.c.last_message_at.is_(None),
                        Owner.updated_at,
                    ),
                    else_=func.greatest(message_count.c.last_message_at, Owner.updated_at),
                ).desc()
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()

    items = [
        {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "instance_count": int(row.instance_count),
            "knowledge_count": int(row.knowledge_count),
            "message_count": int(row.message_count),
            "last_active_at": row.last_active_at,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


async def get_owner_detail(db: AsyncSession, owner_id: str) -> dict[str, Any] | None:
    owner = await db.scalar(select(Owner).where(Owner.id == owner_id))
    if owner is None:
        return None

    instance_count = (
        await db.execute(
            select(func.count(ModelInstance.id)).where(ModelInstance.owner_id == owner_id)
        )
    ).scalar_one()
    knowledge_count = (
        await db.execute(
            select(func.count(KnowledgeEntry.id)).where(KnowledgeEntry.owner_id == owner_id)
        )
    ).scalar_one()
    thread_count = (
        await db.execute(
            select(func.count(ConversationThread.id)).where(
                ConversationThread.owner_id == owner_id
            )
        )
    ).scalar_one()
    message_count_result = (
        await db.execute(
            select(func.count(Message.id), func.max(Message.created_at))
            .join(ConversationThread, ConversationThread.id == Message.thread_id)
            .where(ConversationThread.owner_id == owner_id)
        )
    ).one()

    return {
        "id": owner.id,
        "name": owner.name,
        "email": owner.email,
        "phone": owner.phone,
        "preferred_language": owner.preferred_language,
        "instance_count": int(instance_count),
        "knowledge_count": int(knowledge_count),
        "message_count": int(message_count_result[0] or 0),
        "thread_count": int(thread_count),
        "last_active_at": message_count_result[1] or owner.updated_at,
        "created_at": owner.created_at,
        "updated_at": owner.updated_at,
    }
