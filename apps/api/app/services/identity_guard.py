"""Identity protection system — monitors for anomalies and triggers challenges."""

import json
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime

import redis.asyncio as aioredis
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.config import settings
from app.models.identity import (
    AnomalyType,
    ChallengeLevel,
    ChallengePayload,
    ChallengeResult,
    ChallengeResponse,
    GuardCheckResult,
    SuspicionEvent,
)
from app.models.owner import Owner
from app.models.voice import VerificationLog

logger = logging.getLogger(__name__)

# Redis key prefixes
SUSPICION_PREFIX = "guard:suspicion:"
SESSION_STATS_PREFIX = "guard:stats:"
CHALLENGE_PREFIX = "guard:challenge:"
LOCKOUT_PREFIX = "guard:lockout:"
SUSPICION_TTL = 3600
SESSION_STATS_TTL = 7200
CHALLENGE_TTL = 300
LOCKOUT_TTL = 1800

# Anomaly score weights
SCORE_TYPING_ANOMALY = 15
SCORE_LANGUAGE_SWITCH = 20
SCORE_SENSITIVE_TOPIC = 25
SCORE_FAILED_VERIFICATION = 30
SCORE_NEW_DEVICE = 15
SCORE_UNUSUAL_HOURS = 10

# Thresholds
THRESHOLD_SOFT = 30
THRESHOLD_HARD = 60
THRESHOLD_LOCKOUT = 80

SENSITIVE_KEYWORDS = {
    "password", "credit card", "ssn", "social security", "bank account",
    "pin number", "routing number", "secret", "private key", "seed phrase",
    "wallet", "transfer money", "wire transfer", "account number",
    "delete all", "erase everything", "remove my data",
}


def _generate_id() -> str:
    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _is_unusual_hour(hour: int) -> bool:
    return 1 <= hour < 5


class IdentityGuard:
    """Monitors interactions for anomalies and triggers identity challenges.

    Uses the AI service for LLM-based operations instead of direct Ollama calls.
    """

    def __init__(self, ai_client: AIServiceClient | None = None) -> None:
        self.ai = ai_client or get_ai_client()

    # -- Main entry point --

    async def check(
        self,
        owner_id: str,
        message: str,
        role: str,
        db: AsyncSession,
        r: aioredis.Redis,
        session_id: str | None = None,
        client_ip: str | None = None,
    ) -> GuardCheckResult:
        if await self._is_locked_out(owner_id, r):
            return GuardCheckResult(
                suspicion_score=100,
                challenge_level=ChallengeLevel.lockout,
                anomalies=["already_locked_out"],
            )

        if role != "owner":
            return GuardCheckResult(
                suspicion_score=0,
                challenge_level=ChallengeLevel.none,
            )

        current_score = await self._get_score(owner_id, r)
        anomalies: list[str] = []

        delta, detected = await self._check_typing_pattern(owner_id, message, r)
        if detected:
            current_score += delta
            anomalies.append(f"typing_anomaly (+{delta})")
            await self._record_event(owner_id, AnomalyType.typing_anomaly, delta, detected, session_id, db)

        delta, detected = await self._check_language_switch(owner_id, message, db, r)
        if detected:
            current_score += delta
            anomalies.append(f"language_switch (+{delta})")
            await self._record_event(owner_id, AnomalyType.language_switch, delta, detected, session_id, db)

        delta, detected = self._check_sensitive_topic(message)
        if detected:
            current_score += delta
            anomalies.append(f"sensitive_topic (+{delta})")
            await self._record_event(owner_id, AnomalyType.sensitive_topic, delta, detected, session_id, db)

        delta, detected = await self._check_failed_verifications(owner_id, db)
        if detected:
            current_score += delta
            anomalies.append(f"failed_verification (+{delta})")
            await self._record_event(owner_id, AnomalyType.failed_verification, delta, detected, session_id, db)

        delta, detected = await self._check_new_device(owner_id, client_ip, r)
        if detected:
            current_score += delta
            anomalies.append(f"new_device (+{delta})")
            await self._record_event(owner_id, AnomalyType.new_device, delta, detected, session_id, db)

        delta, detected = self._check_unusual_hours()
        if detected:
            current_score += delta
            anomalies.append(f"unusual_hours (+{delta})")
            await self._record_event(owner_id, AnomalyType.unusual_hours, delta, detected, session_id, db)

        current_score = max(0, min(100, current_score))
        await self._set_score(owner_id, current_score, r)
        await self._update_session_stats(owner_id, message, r)

        if anomalies:
            await db.commit()

        level = ChallengeLevel.none
        challenge: ChallengePayload | None = None

        if current_score >= THRESHOLD_LOCKOUT:
            level = ChallengeLevel.lockout
            await self._lock_out(owner_id, r)
        elif current_score >= THRESHOLD_HARD:
            level = ChallengeLevel.hard
            challenge = await self._create_hard_challenge(owner_id, r)
        elif current_score >= THRESHOLD_SOFT:
            level = ChallengeLevel.soft
            challenge = await self._create_soft_challenge(owner_id, db, r)

        return GuardCheckResult(
            suspicion_score=current_score,
            challenge_level=level,
            anomalies=anomalies,
            challenge=challenge,
        )

    # -- Challenge evaluation --

    async def evaluate_challenge(
        self,
        owner_id: str,
        response: ChallengeResponse,
        db: AsyncSession,
        r: aioredis.Redis,
    ) -> ChallengeResult:
        raw = await r.get(f"{CHALLENGE_PREFIX}{response.challenge_id}")
        if not raw:
            return ChallengeResult(
                passed=False,
                message="Challenge expired or not found.",
                new_score=await self._get_score(owner_id, r),
            )

        challenge_data = json.loads(raw)
        challenge_type = challenge_data.get("type")
        passed = False

        if challenge_type == "soft":
            passed = await self._evaluate_soft_answer(
                question=challenge_data.get("question", ""),
                expected_fact=challenge_data.get("expected_fact", ""),
                user_answer=response.answer or "",
            )
        elif challenge_type == "hard":
            if response.method == "secret_word":
                passed = await self._verify_secret(owner_id, response.value or "", db)

        await r.delete(f"{CHALLENGE_PREFIX}{response.challenge_id}")

        current_score = await self._get_score(owner_id, r)
        if passed:
            current_score = max(0, current_score - 40)
            await self._set_score(owner_id, current_score, r)
            await r.delete(f"{LOCKOUT_PREFIX}{owner_id}")
        else:
            current_score = min(100, current_score + 20)
            await self._set_score(owner_id, current_score, r)

        return ChallengeResult(
            passed=passed,
            message="Challenge passed. Identity confirmed." if passed else "Challenge failed.",
            new_score=current_score,
        )

    # -- Anomaly detectors --

    async def _check_typing_pattern(
        self, owner_id: str, message: str, r: aioredis.Redis
    ) -> tuple[int, str]:
        stats = await self._get_session_stats(owner_id, r)
        if stats is None or stats.get("msg_count", 0) < 5:
            return 0, ""

        avg_len = stats.get("avg_length", 0)
        current_len = len(message)

        if avg_len == 0:
            return 0, ""

        ratio = current_len / avg_len
        if ratio > 3.0:
            return SCORE_TYPING_ANOMALY, f"Message {ratio:.1f}x longer than average ({current_len} vs {avg_len:.0f})"
        if ratio < 0.2 and current_len < 5:
            return SCORE_TYPING_ANOMALY, f"Message unusually short ({current_len} vs avg {avg_len:.0f})"

        return 0, ""

    async def _check_language_switch(
        self, owner_id: str, message: str, db: AsyncSession, r: aioredis.Redis
    ) -> tuple[int, str]:
        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None or owner.preferred_language == "en":
            return 0, ""

        try:
            from langdetect import detect
            detected_lang = detect(message)
        except Exception:
            return 0, ""

        if detected_lang != owner.preferred_language and len(message) > 20:
            return SCORE_LANGUAGE_SWITCH, f"Expected {owner.preferred_language}, detected {detected_lang}"

        return 0, ""

    def _check_sensitive_topic(self, message: str) -> tuple[int, str]:
        lower = message.lower()
        found = [kw for kw in SENSITIVE_KEYWORDS if kw in lower]
        if found:
            return SCORE_SENSITIVE_TOPIC, f"Sensitive keywords: {', '.join(found[:3])}"
        return 0, ""

    async def _check_failed_verifications(
        self, owner_id: str, db: AsyncSession
    ) -> tuple[int, str]:
        cutoff = datetime.now(UTC).replace(tzinfo=None)
        from datetime import timedelta
        cutoff = cutoff - timedelta(minutes=15)

        result = await db.execute(
            select(sa_func.count(VerificationLog.id)).where(
                VerificationLog.owner_id == owner_id,
                VerificationLog.success == False,  # noqa: E712
                VerificationLog.created_at >= cutoff,
            )
        )
        count = result.scalar() or 0

        if count >= 2:
            return SCORE_FAILED_VERIFICATION, f"{count} failed verifications in last 15 min"
        return 0, ""

    async def _check_new_device(
        self, owner_id: str, client_ip: str | None, r: aioredis.Redis
    ) -> tuple[int, str]:
        if not client_ip:
            return 0, ""

        key = f"guard:known_ips:{owner_id}"
        known_ips_raw = await r.get(key)
        known_ips: list[str] = json.loads(known_ips_raw) if known_ips_raw else []

        if client_ip not in known_ips:
            known_ips.append(client_ip)
            known_ips = known_ips[-10:]
            await r.setex(key, 86400 * 30, json.dumps(known_ips))

            if len(known_ips) > 1:
                return SCORE_NEW_DEVICE, f"New IP: {client_ip}"

        return 0, ""

    def _check_unusual_hours(self) -> tuple[int, str]:
        now = datetime.now(UTC)
        if _is_unusual_hour(now.hour):
            return SCORE_UNUSUAL_HOURS, f"Activity at {now.hour}:00 UTC"
        return 0, ""

    # -- Soft challenge (personal question from knowledge) --

    async def _create_soft_challenge(
        self, owner_id: str, db: AsyncSession, r: aioredis.Redis
    ) -> ChallengePayload:
        challenge_id = str(uuid.uuid4())

        question = "Can you tell me something about yourself to confirm your identity?"
        expected_fact = ""

        try:
            # Search for personal facts via AI service
            search_result = await self.ai.vector_search(
                owner_id=owner_id,
                query="personal facts about me: name, pet, favorite, hobby, family",
                top_k=5,
            )

            results = search_result.get("results", [])
            if results:
                fact_texts = [r.get("content_preview") for r in results if r.get("content_preview")]
                if fact_texts:
                    facts_block = "\n".join(f"- {f}" for f in fact_texts[:3])
                    prompt = (
                        "You are creating a casual identity verification question. "
                        "Based on these personal facts, generate ONE short, natural question "
                        "that only the real person would know the answer to. "
                        "Make it sound casual, like a friend checking in. "
                        "Also output the expected answer on a separate line prefixed with ANSWER: \n\n"
                        f"Facts:\n{facts_block}\n\n"
                        "Output format:\nQUESTION: <the question>\nANSWER: <expected answer>"
                    )
                    resp = await self.ai.generate(prompt, temperature=0.4, max_tokens=200)
                    raw_text = resp.get("response", "")

                    for line in raw_text.splitlines():
                        line = line.strip()
                        if line.upper().startswith("QUESTION:"):
                            question = line[len("QUESTION:"):].strip()
                        elif line.upper().startswith("ANSWER:"):
                            expected_fact = line[len("ANSWER:"):].strip()
        except Exception:
            logger.exception("Failed to generate soft challenge question")

        await r.setex(
            f"{CHALLENGE_PREFIX}{challenge_id}",
            CHALLENGE_TTL,
            json.dumps({
                "type": "soft",
                "question": question,
                "expected_fact": expected_fact,
                "owner_id": owner_id,
            }),
        )

        return ChallengePayload(
            challenge_id=challenge_id,
            challenge_type=ChallengeLevel.soft,
            question=question,
            timeout_seconds=60,
        )

    async def _create_hard_challenge(
        self, owner_id: str, r: aioredis.Redis
    ) -> ChallengePayload:
        challenge_id = str(uuid.uuid4())

        methods = ["secret_word", "voice_match"]

        await r.setex(
            f"{CHALLENGE_PREFIX}{challenge_id}",
            CHALLENGE_TTL,
            json.dumps({
                "type": "hard",
                "owner_id": owner_id,
                "methods": methods,
            }),
        )

        return ChallengePayload(
            challenge_id=challenge_id,
            challenge_type=ChallengeLevel.hard,
            methods=methods,
            timeout_seconds=120,
        )

    # -- Challenge evaluation helpers --

    async def _evaluate_soft_answer(
        self, question: str, expected_fact: str, user_answer: str
    ) -> bool:
        if not expected_fact or not user_answer:
            return False

        prompt = (
            "You are an identity verification judge. "
            "Determine if the user's answer matches the expected answer. "
            "Be lenient with exact wording — accept synonyms, partial matches, "
            "and minor differences. Output ONLY 'PASS' or 'FAIL'.\n\n"
            f"Question: {question}\n"
            f"Expected answer: {expected_fact}\n"
            f"User's answer: {user_answer}\n\n"
            "Verdict:"
        )
        try:
            resp = await self.ai.generate(prompt, temperature=0.0, max_tokens=10)
            verdict = resp.get("response", "").strip().upper()
            return "PASS" in verdict
        except Exception:
            logger.exception("Failed to evaluate soft challenge answer")
            return False

    async def _verify_secret(self, owner_id: str, value: str, db: AsyncSession) -> bool:
        from app.core.security import verify_secret

        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None or not owner.auth_secret_hash:
            return False
        return verify_secret(value, owner.auth_secret_hash)

    # -- Redis helpers --

    async def _get_score(self, owner_id: str, r: aioredis.Redis) -> int:
        raw = await r.get(f"{SUSPICION_PREFIX}{owner_id}")
        return int(raw) if raw else 0

    async def _set_score(self, owner_id: str, score: int, r: aioredis.Redis) -> None:
        await r.setex(f"{SUSPICION_PREFIX}{owner_id}", SUSPICION_TTL, str(score))

    async def _is_locked_out(self, owner_id: str, r: aioredis.Redis) -> bool:
        return bool(await r.get(f"{LOCKOUT_PREFIX}{owner_id}"))

    async def _lock_out(self, owner_id: str, r: aioredis.Redis) -> None:
        await r.setex(f"{LOCKOUT_PREFIX}{owner_id}", LOCKOUT_TTL, "1")
        logger.warning("Owner %s locked out due to high suspicion score", owner_id)

    async def _get_session_stats(self, owner_id: str, r: aioredis.Redis) -> dict | None:
        raw = await r.get(f"{SESSION_STATS_PREFIX}{owner_id}")
        return json.loads(raw) if raw else None

    async def _update_session_stats(
        self, owner_id: str, message: str, r: aioredis.Redis
    ) -> None:
        stats = await self._get_session_stats(owner_id, r)
        if stats is None:
            stats = {"msg_count": 0, "total_length": 0, "avg_length": 0.0, "last_ts": 0.0}

        stats["msg_count"] += 1
        stats["total_length"] += len(message)
        stats["avg_length"] = stats["total_length"] / stats["msg_count"]
        stats["last_ts"] = time.time()

        await r.setex(
            f"{SESSION_STATS_PREFIX}{owner_id}",
            SESSION_STATS_TTL,
            json.dumps(stats),
        )

    async def _record_event(
        self,
        owner_id: str,
        event_type: AnomalyType,
        score_delta: int,
        detail: str,
        session_id: str | None,
        db: AsyncSession,
    ) -> None:
        event = SuspicionEvent(
            id=_generate_id(),
            owner_id=owner_id,
            event_type=event_type.value,
            score_delta=score_delta,
            detail=detail,
            session_id=session_id,
        )
        db.add(event)

    # -- Score reset --

    async def reset_score(self, owner_id: str, r: aioredis.Redis) -> None:
        await r.delete(f"{SUSPICION_PREFIX}{owner_id}")
        await r.delete(f"{LOCKOUT_PREFIX}{owner_id}")
        await r.delete(f"{SESSION_STATS_PREFIX}{owner_id}")


# -- Singleton --


_identity_guard: IdentityGuard | None = None


def get_identity_guard() -> IdentityGuard:
    global _identity_guard
    if _identity_guard is None:
        _identity_guard = IdentityGuard()
    return _identity_guard
