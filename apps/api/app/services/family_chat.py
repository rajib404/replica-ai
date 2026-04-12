"""Family conversation handler: custom system prompts, topic filtering, notifications."""

import json
import logging
import uuid

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient
from app.models.chat import (
    ConversationThread,
    Message,
    MessageRole,
    ParticipantType,
)
from app.models.owner import AccessRule, LegacyConfig, Owner
from app.services.conversation import ConversationManager

logger = logging.getLogger(__name__)

# Redis keys for family session tracking
FAMILY_SESSION_PREFIX = "family:session:"
FAMILY_SESSION_TTL = 3600  # 1 hour
FAMILY_NOTIFY_CHANNEL = "family:notifications:{owner_id}"

FAMILY_SYSTEM_PROMPT = """\
You are the AI replica of {owner_name}. \
You are speaking with {grantee_name}, who is your {relation}. \
Share memories and knowledge as {owner_name} would. \
Speak {language}. \
{topic_instructions}\
Respond warmly and maintain {owner_name}'s personality. \
If you don't have information, say so honestly rather than guessing. \
Cite which memories you're drawing from by referencing their [Source N] tags."""

LEGACY_ADDENDUM = """\
Note: {owner_name} is no longer available in person. \
You carry their memories, wisdom, and love. \
Treat this conversation with special care and warmth. \
Help {grantee_name} feel connected to {owner_name}'s legacy."""

RESTRICTED_TOPIC_RESPONSE = (
    "{owner_name} preferred to keep that private. "
    "Is there something else I can share with you?"
)


class FamilyConversationHandler:
    """Handles family member chat sessions with topic-aware prompts and monitoring."""

    def __init__(self) -> None:
        self._conv = ConversationManager()

    # ── System prompt construction ────────────────────────

    def build_family_system_prompt(
        self,
        owner_name: str,
        language: str,
        grantee_name: str,
        relation: str | None,
        allowed_topics: list[str] | None,
        blocked_topics: list[str] | None,
        legacy_mode: bool = False,
    ) -> str:
        # Build topic instructions
        topic_parts: list[str] = []
        if allowed_topics:
            topic_parts.append(
                f"You can discuss: {', '.join(allowed_topics)}. "
            )
        if blocked_topics:
            topic_parts.append(
                f"Do not discuss: {', '.join(blocked_topics)}. "
                f"If asked about these topics, say: "
                f'"{RESTRICTED_TOPIC_RESPONSE.format(owner_name=owner_name)}" '
            )
        topic_instructions = "".join(topic_parts) if topic_parts else ""

        prompt = FAMILY_SYSTEM_PROMPT.format(
            owner_name=owner_name,
            grantee_name=grantee_name,
            relation=relation or "family member",
            language=language,
            topic_instructions=topic_instructions,
        )

        if legacy_mode:
            prompt += "\n" + LEGACY_ADDENDUM.format(
                owner_name=owner_name,
                grantee_name=grantee_name,
            )

        return prompt

    # ── Check if message touches restricted topics ────────

    @staticmethod
    def check_topic_restriction(
        message: str,
        blocked_topics: list[str] | None,
    ) -> bool:
        """Returns True if the message appears to touch a blocked topic."""
        if not blocked_topics:
            return False
        msg_lower = message.lower()
        for topic in blocked_topics:
            # Simple keyword matching — the system prompt also enforces this
            # but we add a hard filter for extra safety
            keywords = topic.lower().split()
            if all(kw in msg_lower for kw in keywords):
                return True
        return False

    # ── Core message processing ───────────────────────────

    async def process_family_message(
        self,
        owner_id: str,
        grantee_name: str,
        relation: str | None,
        access_level: str,
        rule_id: str,
        topic_restrictions: dict | None,
        time_restrictions: dict | None,
        text: str,
        thread_id: str | None,
        db: AsyncSession,
        r: aioredis.Redis,
        ai: AIServiceClient,
    ) -> tuple[str, str, str, list[dict]]:
        """Process a family member message. Returns (response, msg_id, thread_id, sources)."""

        # Resolve owner
        owner_result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = owner_result.scalar_one_or_none()
        owner_name = owner.name if owner else "the owner"
        owner_lang = owner.preferred_language if owner else "en"

        # Parse topic restrictions
        allowed_topics = None
        blocked_topics = None
        if topic_restrictions:
            allowed_topics = topic_restrictions.get("allowed", [])
            blocked_topics = topic_restrictions.get("blocked", [])

        # Check hard block on restricted topics
        if self.check_topic_restriction(text, blocked_topics):
            refusal = RESTRICTED_TOPIC_RESPONSE.format(owner_name=owner_name)

            # Still save to thread for audit trail
            thread = await self._conv.get_or_create_thread(
                owner_id=owner_id,
                participant_type=ParticipantType.family_member,
                participant_name=grantee_name,
                db=db,
                thread_id=thread_id,
            )
            await self._conv.save_message(
                thread_id=thread.id, role=MessageRole.user, content=text, db=db
            )
            assistant_msg = await self._conv.save_message(
                thread_id=thread.id, role=MessageRole.assistant, content=refusal, db=db
            )
            await db.commit()

            # Track session
            await self._track_session(
                r, owner_id, thread.id, grantee_name, relation, access_level
            )

            return refusal, assistant_msg.id, thread.id, []

        # Check legacy mode
        legacy_result = await db.execute(
            select(LegacyConfig).where(
                LegacyConfig.owner_id == owner_id,
                LegacyConfig.is_active == True,  # noqa: E712
            )
        )
        legacy_active = legacy_result.scalar_one_or_none() is not None

        # Build system prompt
        system_prompt = self.build_family_system_prompt(
            owner_name=owner_name,
            language=owner_lang,
            grantee_name=grantee_name,
            relation=relation,
            allowed_topics=allowed_topics,
            blocked_topics=blocked_topics,
            legacy_mode=legacy_active,
        )

        # Get or create thread
        thread = await self._conv.get_or_create_thread(
            owner_id=owner_id,
            participant_type=ParticipantType.family_member,
            participant_name=grantee_name,
            db=db,
            thread_id=thread_id,
        )

        # Save user message
        await self._conv.save_message(
            thread_id=thread.id, role=MessageRole.user, content=text, db=db
        )

        # Load context
        context = await self._conv.load_context(thread.id, db, r)

        # Call AI RAG (non-streaming)
        rag_result = await ai.rag_generate(
            owner_id=owner_id,
            message=text,
            conversation_history=context,
            system_prompt=system_prompt,
        )
        response_text = rag_result.get("response", "")
        sources = rag_result.get("sources", [])

        # Save assistant message
        assistant_msg = await self._conv.save_message(
            thread_id=thread.id,
            role=MessageRole.assistant,
            content=response_text,
            db=db,
        )
        await db.commit()

        # Summarization check
        try:
            await self._conv.maybe_summarize(thread.id, db, r, ai)
        except Exception:
            logger.exception("Family chat summarization failed")

        # Track session
        await self._track_session(
            r, owner_id, thread.id, grantee_name, relation, access_level
        )

        # Notify owner
        await self._notify_owner(
            r, owner_id, grantee_name, thread.id, "message", text[:100]
        )

        return response_text, assistant_msg.id, thread.id, sources

    # ── Streaming variant ─────────────────────────────────

    async def prepare_family_stream(
        self,
        owner_id: str,
        grantee_name: str,
        relation: str | None,
        access_level: str,
        rule_id: str,
        topic_restrictions: dict | None,
        text: str,
        thread_id: str | None,
        db: AsyncSession,
        r: aioredis.Redis,
    ) -> tuple[str | None, str, str, str]:
        """Prepare for streaming: save user msg, build prompt, return refusal if topic blocked.

        Returns (refusal_or_none, system_prompt, thread_id, assistant_msg_id_placeholder).
        """
        owner_result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = owner_result.scalar_one_or_none()
        owner_name = owner.name if owner else "the owner"
        owner_lang = owner.preferred_language if owner else "en"

        allowed_topics = None
        blocked_topics = None
        if topic_restrictions:
            allowed_topics = topic_restrictions.get("allowed", [])
            blocked_topics = topic_restrictions.get("blocked", [])

        thread = await self._conv.get_or_create_thread(
            owner_id=owner_id,
            participant_type=ParticipantType.family_member,
            participant_name=grantee_name,
            db=db,
            thread_id=thread_id,
        )

        await self._conv.save_message(
            thread_id=thread.id, role=MessageRole.user, content=text, db=db
        )

        # Hard topic check
        if self.check_topic_restriction(text, blocked_topics):
            refusal = RESTRICTED_TOPIC_RESPONSE.format(owner_name=owner_name)
            assistant_msg = await self._conv.save_message(
                thread_id=thread.id,
                role=MessageRole.assistant,
                content=refusal,
                db=db,
            )
            await db.commit()
            await self._track_session(
                r, owner_id, thread.id, grantee_name, relation, access_level
            )
            return refusal, "", thread.id, assistant_msg.id

        # Legacy check
        legacy_result = await db.execute(
            select(LegacyConfig).where(
                LegacyConfig.owner_id == owner_id,
                LegacyConfig.is_active == True,  # noqa: E712
            )
        )
        legacy_active = legacy_result.scalar_one_or_none() is not None

        system_prompt = self.build_family_system_prompt(
            owner_name=owner_name,
            language=owner_lang,
            grantee_name=grantee_name,
            relation=relation,
            allowed_topics=allowed_topics,
            blocked_topics=blocked_topics,
            legacy_mode=legacy_active,
        )

        await db.commit()

        await self._track_session(
            r, owner_id, thread.id, grantee_name, relation, access_level
        )
        await self._notify_owner(
            r, owner_id, grantee_name, thread.id, "message", text[:100]
        )

        return None, system_prompt, thread.id, ""

    # ── Session tracking ──────────────────────────────────

    async def _track_session(
        self,
        r: aioredis.Redis,
        owner_id: str,
        thread_id: str,
        grantee_name: str,
        relation: str | None,
        access_level: str,
    ) -> None:
        """Track an active family session in Redis."""
        key = f"{FAMILY_SESSION_PREFIX}{owner_id}:{thread_id}"
        session_data = json.dumps({
            "thread_id": thread_id,
            "grantee_name": grantee_name,
            "grantee_relation": relation,
            "access_level": access_level,
        })
        await r.setex(key, FAMILY_SESSION_TTL, session_data)

    async def get_active_sessions(
        self,
        owner_id: str,
        r: aioredis.Redis,
        db: AsyncSession,
    ) -> list[dict]:
        """Get all active family sessions for an owner."""
        pattern = f"{FAMILY_SESSION_PREFIX}{owner_id}:*"
        sessions = []
        async for key in r.scan_iter(match=pattern):
            raw = await r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            thread_id = data["thread_id"]

            # Get message count and last message time
            count_result = await db.execute(
                select(func.count(Message.id)).where(Message.thread_id == thread_id)
            )
            msg_count = count_result.scalar() or 0

            last_msg_result = await db.execute(
                select(Message.created_at)
                .where(Message.thread_id == thread_id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            last_msg_at = last_msg_result.scalar_one_or_none()

            thread_result = await db.execute(
                select(ConversationThread.created_at).where(
                    ConversationThread.id == thread_id
                )
            )
            started_at = thread_result.scalar_one_or_none()

            sessions.append({
                "thread_id": thread_id,
                "grantee_name": data["grantee_name"],
                "grantee_relation": data.get("grantee_relation"),
                "access_level": data["access_level"],
                "message_count": msg_count,
                "last_message_at": last_msg_at,
                "started_at": started_at,
            })

        return sessions

    # ── Owner notification ────────────────────────────────

    async def _notify_owner(
        self,
        r: aioredis.Redis,
        owner_id: str,
        grantee_name: str,
        thread_id: str,
        event: str,
        detail: str | None = None,
    ) -> None:
        """Publish a notification to the owner's channel."""
        channel = FAMILY_NOTIFY_CHANNEL.format(owner_id=owner_id)
        payload = json.dumps({
            "type": "family_session",
            "event": event,
            "grantee_name": grantee_name,
            "thread_id": thread_id,
            "detail": detail,
        })
        try:
            await r.publish(channel, payload)
        except Exception:
            logger.exception("Failed to publish family notification")

    # ── Owner intervention ────────────────────────────────

    async def owner_intervene(
        self,
        owner_id: str,
        thread_id: str,
        message_text: str,
        db: AsyncSession,
    ) -> tuple[str, str]:
        """Owner sends a message through the replica into a family conversation.

        The message is saved as an assistant message (the replica speaking
        on behalf of the owner). Returns (message_id, thread_id).
        """
        # Verify thread belongs to this owner
        thread_result = await db.execute(
            select(ConversationThread).where(
                ConversationThread.id == thread_id,
                ConversationThread.owner_id == owner_id,
            )
        )
        thread = thread_result.scalar_one_or_none()
        if not thread:
            raise ValueError("Thread not found")

        msg = await self._conv.save_message(
            thread_id=thread.id,
            role=MessageRole.assistant,
            content=message_text,
            db=db,
        )
        await db.commit()
        return msg.id, thread.id

    # ── Analytics ─────────────────────────────────────────

    async def get_family_analytics(
        self, owner_id: str, db: AsyncSession
    ) -> dict:
        """Compute per-member analytics for an owner's family conversations."""
        # Get all family threads
        result = await db.execute(
            select(ConversationThread).where(
                ConversationThread.owner_id == owner_id,
                ConversationThread.participant_type == ParticipantType.family_member,
            )
        )
        threads = list(result.scalars().all())

        # Group by participant name
        members: dict[str, dict] = {}
        total_msgs = 0
        for thread in threads:
            name = thread.participant_name
            if name not in members:
                members[name] = {
                    "grantee_name": name,
                    "grantee_relation": None,
                    "total_sessions": 0,
                    "total_messages": 0,
                    "last_visit_at": None,
                    "top_topics": [],
                }

            members[name]["total_sessions"] += 1

            # Count messages in this thread
            count_result = await db.execute(
                select(func.count(Message.id)).where(
                    Message.thread_id == thread.id,
                    Message.role == MessageRole.user,
                )
            )
            msg_count = count_result.scalar() or 0
            members[name]["total_messages"] += msg_count
            total_msgs += msg_count

            # Last message time
            last_result = await db.execute(
                select(Message.created_at)
                .where(Message.thread_id == thread.id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            last_at = last_result.scalar_one_or_none()
            if last_at:
                prev = members[name]["last_visit_at"]
                if prev is None or last_at > prev:
                    members[name]["last_visit_at"] = last_at

        # Try to resolve relations from access rules
        for name, data in members.items():
            rule_result = await db.execute(
                select(AccessRule.grantee_relation).where(
                    AccessRule.owner_id == owner_id,
                    AccessRule.grantee_name == name,
                ).limit(1)
            )
            rel = rule_result.scalar_one_or_none()
            if rel:
                data["grantee_relation"] = rel

        return {
            "members": list(members.values()),
            "total_family_messages": total_msgs,
            "total_family_sessions": len(threads),
        }

    # ── Session info for family member ────────────────────

    async def get_family_session_info(
        self,
        owner_id: str,
        grantee_name: str,
        access_level: str,
        rule_id: str,
        db: AsyncSession,
    ) -> dict:
        """Return session info for the family member's UI."""
        owner_result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = owner_result.scalar_one_or_none()

        # Check legacy mode
        legacy_result = await db.execute(
            select(LegacyConfig).where(
                LegacyConfig.owner_id == owner_id,
                LegacyConfig.is_active == True,  # noqa: E712
            )
        )
        legacy_active = legacy_result.scalar_one_or_none() is not None

        # Get topic/time restrictions from access rule
        rule_result = await db.execute(
            select(AccessRule).where(AccessRule.id == rule_id)
        )
        rule = rule_result.scalar_one_or_none()

        return {
            "owner_id": owner_id,
            "owner_name": owner.name if owner else "Unknown",
            "grantee_name": grantee_name,
            "access_level": access_level,
            "topic_restrictions": rule.topic_restrictions if rule else None,
            "time_restrictions": rule.time_restrictions if rule else None,
            "legacy_mode_active": legacy_active,
        }
