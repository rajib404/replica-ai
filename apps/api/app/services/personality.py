"""Personality analysis and emotional support services.

PersonalityTracker learns owner personality from message history.
EmotionalSupport detects emotions and generates supportive responses.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient
from app.models.chat import Message, MessageRole
from app.models.owner import EmotionLog, PersonalityProfile

logger = logging.getLogger(__name__)

ANALYSIS_BATCH_SIZE = 100  # Analyze every N messages
MIN_MESSAGES_FOR_ANALYSIS = 50


def _extract_json(text: str) -> dict | list | None:
    """Extract JSON from a possibly messy LLM response."""
    text = text.strip()
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    if start == -1:
        return None
    end = max(text.rfind("}"), text.rfind("]"))
    if end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class PersonalityTracker:
    """Learns and maintains a personality profile from owner messages."""

    @staticmethod
    async def get_profile(
        owner_id: str, db: AsyncSession
    ) -> PersonalityProfile | None:
        result = await db.execute(
            select(PersonalityProfile).where(
                PersonalityProfile.owner_id == owner_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_profile(
        owner_id: str, db: AsyncSession
    ) -> PersonalityProfile:
        profile = await PersonalityTracker.get_profile(owner_id, db)
        if profile:
            return profile

        profile = PersonalityProfile(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            traits={},
            communication_style={},
            humor_patterns={},
            values_and_beliefs={},
            phrases_and_idioms=[],
            emotional_baseline={},
            messages_analyzed=0,
            owner_confirmed={},
        )
        db.add(profile)
        await db.flush()
        return profile

    @staticmethod
    async def should_analyze(owner_id: str, db: AsyncSession) -> bool:
        """Check if enough new messages have accumulated for re-analysis."""
        profile = await PersonalityTracker.get_profile(owner_id, db)
        analyzed = profile.messages_analyzed if profile else 0

        count_result = await db.execute(
            select(func.count(Message.id)).where(
                Message.role == MessageRole.user,
                Message.thread_id.in_(
                    select(Message.thread_id).where(
                        Message.content_text.isnot(None)
                    )
                ),
            )
        )
        # Count owner messages via thread ownership
        from app.models.chat import ConversationThread, ParticipantType

        total_result = await db.execute(
            select(func.count(Message.id))
            .join(
                ConversationThread,
                Message.thread_id == ConversationThread.id,
            )
            .where(
                ConversationThread.owner_id == owner_id,
                ConversationThread.participant_type == ParticipantType.owner,
                Message.role == MessageRole.user,
            )
        )
        total = total_result.scalar() or 0

        if total < MIN_MESSAGES_FOR_ANALYSIS:
            return False
        return (total - analyzed) >= ANALYSIS_BATCH_SIZE

    @staticmethod
    async def analyze_message_batch(
        owner_id: str, db: AsyncSession, ai: AIServiceClient, force: bool = False
    ) -> PersonalityProfile:
        """Analyze recent owner messages and update personality profile.

        Runs Ollama analysis on the latest batch of unanalyzed messages.
        """
        profile = await PersonalityTracker.get_or_create_profile(owner_id, db)

        if not force:
            should = await PersonalityTracker.should_analyze(owner_id, db)
            if not should:
                return profile

        # Load the latest batch of owner messages
        from app.models.chat import ConversationThread, ParticipantType

        result = await db.execute(
            select(Message)
            .join(
                ConversationThread,
                Message.thread_id == ConversationThread.id,
            )
            .where(
                ConversationThread.owner_id == owner_id,
                ConversationThread.participant_type == ParticipantType.owner,
                Message.role == MessageRole.user,
                Message.content_text.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(ANALYSIS_BATCH_SIZE)
        )
        messages = list(result.scalars().all())

        if len(messages) < 10:
            return profile

        # Build the analysis prompt
        message_texts = [m.content_text for m in messages if m.content_text]
        sample = "\n---\n".join(message_texts[:80])

        analysis_prompt = f"""Analyze these messages from a person and extract their personality traits.
Return valid JSON with these exact keys:

{{
  "traits": [
    {{"name": "trait_name", "value": "description", "confidence": 0.0-1.0}}
  ],
  "communication_style": {{
    "formality": "casual|neutral|formal",
    "verbosity": "terse|moderate|verbose",
    "emoji_usage": "none|low|moderate|heavy",
    "tone": "warm|friendly|neutral|professional|blunt"
  }},
  "humor_patterns": {{
    "style": "dry|sarcastic|self_deprecating|puns|observational|none",
    "frequency": "none|low|moderate|high",
    "examples": ["example phrases"]
  }},
  "values_and_beliefs": [
    {{"name": "value_name", "value": "description", "confidence": 0.0-1.0}}
  ],
  "phrases_and_idioms": ["commonly used phrases or expressions"],
  "emotional_baseline": {{
    "happy": 0.0-1.0,
    "sad": 0.0-1.0,
    "anxious": 0.0-1.0,
    "angry": 0.0-1.0,
    "neutral": 0.0-1.0,
    "excited": 0.0-1.0
  }}
}}

Messages:
{sample}"""

        try:
            resp = await ai.generate(
                prompt=analysis_prompt,
                system_prompt="You are a personality analyst. Analyze the writing patterns and return JSON only.",
                temperature=0.3,
                max_tokens=2048,
            )
            raw_text = resp.get("response", "")
            parsed = _extract_json(raw_text)

            if not isinstance(parsed, dict):
                logger.warning("Personality analysis returned non-dict: %s", type(parsed))
                return profile

            # Merge with existing profile, preserving owner confirmations
            confirmed = profile.owner_confirmed or {}

            if "traits" in parsed:
                new_traits = parsed["traits"]
                # Preserve confirmed status from previous analysis
                for trait in new_traits:
                    name = trait.get("name", "")
                    if name in confirmed:
                        trait["confirmed"] = confirmed[name]
                profile.traits = {"items": new_traits}

            if "communication_style" in parsed:
                profile.communication_style = parsed["communication_style"]

            if "humor_patterns" in parsed:
                profile.humor_patterns = parsed["humor_patterns"]

            if "values_and_beliefs" in parsed:
                new_values = parsed["values_and_beliefs"]
                for val in new_values:
                    name = val.get("name", "")
                    key = f"value:{name}"
                    if key in confirmed:
                        val["confirmed"] = confirmed[key]
                profile.values_and_beliefs = {"items": new_values}

            if "phrases_and_idioms" in parsed:
                profile.phrases_and_idioms = parsed["phrases_and_idioms"]

            if "emotional_baseline" in parsed:
                profile.emotional_baseline = parsed["emotional_baseline"]

            profile.messages_analyzed = profile.messages_analyzed + len(messages)
            profile.last_analysis_at = datetime.now(UTC).replace(tzinfo=None)
            await db.flush()

        except Exception:
            logger.exception("Personality analysis failed for owner %s", owner_id)

        return profile

    @staticmethod
    def get_personality_prompt(profile: PersonalityProfile) -> str:
        """Build a system prompt fragment from the personality profile."""
        parts: list[str] = []

        # Communication style
        style = profile.communication_style or {}
        if style:
            formality = style.get("formality", "neutral")
            tone = style.get("tone", "friendly")
            verbosity = style.get("verbosity", "moderate")
            parts.append(
                f"Communication style: {formality} formality, {tone} tone, {verbosity} verbosity."
            )

        # Humor
        humor = profile.humor_patterns or {}
        if humor and humor.get("style") != "none":
            freq = humor.get("frequency", "low")
            style_name = humor.get("style", "")
            parts.append(f"Humor: {style_name} style, used {freq}.")

        # Key traits (only confirmed or high-confidence)
        confirmed = profile.owner_confirmed or {}
        traits_data = profile.traits or {}
        trait_items = traits_data.get("items", []) if isinstance(traits_data, dict) else []
        confirmed_traits = []
        for t in trait_items:
            name = t.get("name", "")
            # Skip rejected traits
            if confirmed.get(name) is False:
                continue
            # Include confirmed or high-confidence traits
            if confirmed.get(name) is True or t.get("confidence", 0) >= 0.7:
                confirmed_traits.append(f"{name}: {t.get('value', '')}")

        if confirmed_traits:
            parts.append("Key personality traits: " + "; ".join(confirmed_traits[:8]) + ".")

        # Phrases
        phrases = profile.phrases_and_idioms or []
        if phrases:
            parts.append(
                "Commonly used phrases: " + ", ".join(f'"{p}"' for p in phrases[:5]) + "."
            )

        # Values (only confirmed or high-confidence)
        values_data = profile.values_and_beliefs or {}
        value_items = values_data.get("items", []) if isinstance(values_data, dict) else []
        confirmed_values = []
        for v in value_items:
            name = v.get("name", "")
            key = f"value:{name}"
            if confirmed.get(key) is False:
                continue
            if confirmed.get(key) is True or v.get("confidence", 0) >= 0.7:
                confirmed_values.append(name)

        if confirmed_values:
            parts.append("Core values: " + ", ".join(confirmed_values[:5]) + ".")

        if not parts:
            return ""

        return (
            "The owner's learned personality profile:\n"
            + "\n".join(parts)
            + "\nMirror these patterns naturally in your responses."
        )


class EmotionalSupport:
    """Detects emotions and generates supportive responses."""

    EMOTIONS = [
        "happy", "sad", "anxious", "angry", "neutral",
        "excited", "lonely", "stressed",
    ]

    SUPPORT_STRATEGIES: dict[str, str] = {
        "sad": "Be empathetic and gently encouraging. Reference positive shared memories if available.",
        "anxious": "Be calming and reassuring. Help break down worries into manageable pieces.",
        "angry": "Acknowledge the frustration without judgment. Help process the emotion constructively.",
        "lonely": "Be warm and present. Remind them of connections and shared experiences.",
        "stressed": "Be practical and supportive. Help prioritize and offer to break tasks down.",
        "happy": "Share in the joy. Be enthusiastic and celebratory.",
        "excited": "Match the energy. Be enthusiastic and encouraging.",
        "neutral": "Be attentive and engaged. Follow the conversational lead.",
    }

    @staticmethod
    async def detect_emotion(
        text: str, ai: AIServiceClient
    ) -> dict:
        """Detect the primary emotion from a message using Ollama.

        Returns dict with: emotion, intensity, secondary_emotions, context_summary
        """
        prompt = f"""Analyze the emotional state of the person who wrote this message.
Return valid JSON:
{{
  "emotion": "one of: happy, sad, anxious, angry, neutral, excited, lonely, stressed",
  "intensity": 0.0-1.0,
  "secondary_emotions": ["list of secondary emotions if any"],
  "context_summary": "brief description of what triggered this emotion"
}}

Message: {text}"""

        try:
            resp = await ai.generate(
                prompt=prompt,
                system_prompt="You are an emotion analyst. Return JSON only.",
                temperature=0.2,
                max_tokens=256,
            )
            raw = resp.get("response", "")
            parsed = _extract_json(raw)

            if isinstance(parsed, dict) and "emotion" in parsed:
                emotion = parsed["emotion"]
                if emotion not in EmotionalSupport.EMOTIONS:
                    emotion = "neutral"
                return {
                    "emotion": emotion,
                    "intensity": min(1.0, max(0.0, float(parsed.get("intensity", 0.5)))),
                    "secondary_emotions": parsed.get("secondary_emotions", []),
                    "context_summary": parsed.get("context_summary"),
                }
        except Exception:
            logger.exception("Emotion detection failed")

        return {
            "emotion": "neutral",
            "intensity": 0.5,
            "secondary_emotions": [],
            "context_summary": None,
        }

    @staticmethod
    async def log_emotion(
        owner_id: str,
        detection: dict,
        db: AsyncSession,
        message_id: str | None = None,
    ) -> EmotionLog:
        """Persist an emotion detection to the database."""
        log = EmotionLog(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            message_id=message_id,
            emotion=detection["emotion"],
            intensity=detection["intensity"],
            secondary_emotions=detection.get("secondary_emotions"),
            context_summary=detection.get("context_summary"),
        )
        db.add(log)
        await db.flush()
        return log

    @staticmethod
    async def get_emotion_trend(
        owner_id: str, db: AsyncSession, days: int = 7
    ) -> list[dict]:
        """Get emotion trend over the past N days, grouped by date."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

        result = await db.execute(
            select(
                func.date(EmotionLog.created_at).label("date"),
                EmotionLog.emotion,
                func.avg(EmotionLog.intensity).label("avg_intensity"),
                func.count(EmotionLog.id).label("count"),
            )
            .where(
                EmotionLog.owner_id == owner_id,
                EmotionLog.created_at >= cutoff,
            )
            .group_by(
                func.date(EmotionLog.created_at),
                EmotionLog.emotion,
            )
            .order_by(func.date(EmotionLog.created_at))
        )
        rows = result.all()

        return [
            {
                "date": str(row.date),
                "emotion": row.emotion,
                "intensity": round(float(row.avg_intensity), 2),
                "count": row.count,
            }
            for row in rows
        ]

    @staticmethod
    async def get_latest_emotion(
        owner_id: str, db: AsyncSession
    ) -> EmotionLog | None:
        result = await db.execute(
            select(EmotionLog)
            .where(EmotionLog.owner_id == owner_id)
            .order_by(EmotionLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def get_support_prompt(emotion: str, intensity: float) -> str:
        """Build a system prompt fragment for emotional support."""
        if emotion == "neutral" or intensity < 0.3:
            return ""

        strategy = EmotionalSupport.SUPPORT_STRATEGIES.get(emotion, "")
        if not strategy:
            return ""

        intensity_label = "mildly" if intensity < 0.5 else "noticeably" if intensity < 0.7 else "very"

        return (
            f"The user seems {intensity_label} {emotion}. "
            f"Emotional support strategy: {strategy}"
        )
