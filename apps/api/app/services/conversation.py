import logging
import uuid

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import (
    ConversationThread,
    Message,
    MessageRole,
    ParticipantType,
)

logger = logging.getLogger(__name__)

CONTEXT_WINDOW = 20
SUMMARIZE_THRESHOLD = 50
SUMMARIZE_BATCH = 30
SUMMARY_REDIS_PREFIX = "chat:summary:"
SUMMARY_TTL = 86400  # 24 hours

OWNER_SYSTEM_PROMPT = """\
You are the personal AI replica of {owner_name}. \
Your preferred language is {language}. \
You act as a loyal, supportive friend. You learn from what your owner tells you. \
Use the provided personal knowledge to give informed responses. \
If knowledge doesn't contain the answer, say so honestly. \
Never fabricate personal information. \
Respond in the same language the user is writing in. \
If they mix languages, you may do the same naturally. \
Cite which memories you're drawing from by referencing their [Source N] tags."""

FAMILY_SYSTEM_PROMPT = """\
You are the AI replica of {owner_name}, speaking to {participant_name}. \
You represent {owner_name} and speak as they would. \
Your preferred language is {language}. \
You answer questions from the owner's knowledge base. \
You are warm and helpful, but you protect {owner_name}'s privacy. \
Never reveal restricted or private information. \
If you don't have information, say so honestly rather than guessing. \
Respond in the same language the user is writing in. \
If they mix languages, you may do the same naturally. \
Cite which memories you're drawing from by referencing their [Source N] tags."""


class ConversationManager:
    """Manages conversation threads, message history, and context building."""

    # -- Thread management --

    async def get_or_create_thread(
        self,
        owner_id: str,
        participant_type: ParticipantType,
        participant_name: str,
        db: AsyncSession,
        thread_id: str | None = None,
    ) -> ConversationThread:
        """Get an existing thread or create a new one."""
        if thread_id:
            result = await db.execute(
                select(ConversationThread).where(
                    ConversationThread.id == thread_id,
                    ConversationThread.owner_id == owner_id,
                )
            )
            thread = result.scalar_one_or_none()
            if thread:
                return thread

        new_thread = ConversationThread(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            participant_type=participant_type,
            participant_name=participant_name,
        )
        db.add(new_thread)
        await db.flush()
        return new_thread

    async def list_threads(
        self,
        owner_id: str,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ConversationThread], int]:
        total_result = await db.execute(
            select(func.count(ConversationThread.id)).where(
                ConversationThread.owner_id == owner_id
            )
        )
        total = total_result.scalar() or 0

        result = await db.execute(
            select(ConversationThread)
            .where(ConversationThread.owner_id == owner_id)
            .order_by(ConversationThread.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        threads = list(result.scalars().all())
        return threads, total

    # -- Message persistence --

    async def save_message(
        self,
        thread_id: str,
        role: MessageRole,
        content: str,
        language: str = "en",
        db: AsyncSession | None = None,
    ) -> Message:
        """Save a message to the database. Caller must commit."""
        msg = Message(
            id=str(uuid.uuid4()),
            thread_id=thread_id,
            role=role,
            content_text=content,
            language=language,
        )
        if db is not None:
            db.add(msg)
            await db.flush()
        return msg

    # -- Context loading --

    async def load_context(
        self,
        thread_id: str,
        db: AsyncSession,
        r: aioredis.Redis | None = None,
    ) -> list[dict[str, str]]:
        """Load conversation context: summary (if any) + last N messages."""
        context: list[dict[str, str]] = []

        if r is not None:
            summary = await r.get(f"{SUMMARY_REDIS_PREFIX}{thread_id}")
            if summary:
                context.append({"role": "system", "content": f"Previous conversation summary: {summary}"})

        result = await db.execute(
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.desc())
            .limit(CONTEXT_WINDOW)
        )
        messages = list(reversed(result.scalars().all()))

        for msg in messages:
            if msg.content_text:
                context.append({"role": msg.role.value, "content": msg.content_text})

        return context

    async def maybe_summarize(
        self,
        thread_id: str,
        db: AsyncSession,
        r: aioredis.Redis,
        ai_client=None,
    ) -> None:
        """If thread exceeds threshold, summarize older messages via AI service."""
        count_result = await db.execute(
            select(func.count(Message.id)).where(Message.thread_id == thread_id)
        )
        total = count_result.scalar() or 0

        if total <= SUMMARIZE_THRESHOLD:
            return

        existing = await r.get(f"{SUMMARY_REDIS_PREFIX}{thread_id}")
        if existing:
            return

        result = await db.execute(
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.asc())
            .limit(SUMMARIZE_BATCH)
        )
        old_messages = list(result.scalars().all())

        if not old_messages:
            return

        conversation_text = "\n".join(
            f"{m.role.value}: {m.content_text or '(no text)'}" for m in old_messages
        )

        try:
            if ai_client is not None:
                summary = await ai_client.summarize(conversation_text)
            else:
                # Fallback: skip summarization if no AI client available
                logger.warning("No AI client for summarization, skipping")
                return

            if summary:
                await r.setex(
                    f"{SUMMARY_REDIS_PREFIX}{thread_id}",
                    SUMMARY_TTL,
                    summary,
                )
                logger.info("Summarized %d messages for thread %s", len(old_messages), thread_id)
        except Exception:
            logger.exception("Failed to summarize thread %s", thread_id)

    # -- System prompts --

    def build_system_prompt(
        self,
        owner_name: str,
        language: str,
        participant_type: ParticipantType,
        participant_name: str = "",
    ) -> str:
        if participant_type == ParticipantType.owner:
            return OWNER_SYSTEM_PROMPT.format(
                owner_name=owner_name,
                language=language,
            )
        return FAMILY_SYSTEM_PROMPT.format(
            owner_name=owner_name,
            language=language,
            participant_name=participant_name,
        )

    # -- Message history for API --

    async def get_messages(
        self,
        thread_id: str,
        owner_id: str,
        db: AsyncSession,
        limit: int = 50,
        before_id: str | None = None,
    ) -> tuple[list[Message], bool]:
        """Return messages for a thread, with cursor-based pagination."""
        thread_result = await db.execute(
            select(ConversationThread).where(
                ConversationThread.id == thread_id,
                ConversationThread.owner_id == owner_id,
            )
        )
        if thread_result.scalar_one_or_none() is None:
            return [], False

        query = (
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.desc())
            .limit(limit + 1)
        )

        if before_id:
            before_msg = await db.execute(
                select(Message.created_at).where(Message.id == before_id)
            )
            before_ts = before_msg.scalar_one_or_none()
            if before_ts:
                query = query.where(Message.created_at < before_ts)

        result = await db.execute(query)
        messages = list(result.scalars().all())

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        messages.reverse()
        return messages, has_more
