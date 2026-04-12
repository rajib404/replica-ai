"""Models for the identity protection system: suspicion events, challenges, lockouts."""

import enum
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.owner import Base, _utcnow


# ─── SQLAlchemy ──────────────────────────────────────────────


class SuspicionEvent(Base):
    """Individual anomaly event that contributed to a suspicion score."""

    __tablename__ = "suspicion_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    # typing_anomaly | language_switch | sensitive_topic | failed_verification
    # new_device | unusual_hours
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


# ─── Pydantic schemas ───────────────────────────────────────


class AnomalyType(str, enum.Enum):
    typing_anomaly = "typing_anomaly"
    language_switch = "language_switch"
    sensitive_topic = "sensitive_topic"
    failed_verification = "failed_verification"
    new_device = "new_device"
    unusual_hours = "unusual_hours"


class ChallengeLevel(str, enum.Enum):
    none = "none"
    soft = "soft"      # 30-60: casual question from knowledge
    hard = "hard"      # 60-80: secret word / voice verification
    lockout = "lockout" # 80+: full re-authentication


class GuardCheckResult(BaseModel):
    """Result of IdentityGuard.check() — tells the caller what action is needed."""
    suspicion_score: int
    challenge_level: ChallengeLevel
    anomalies: list[str] = []
    challenge: "ChallengePayload | None" = None


class ChallengePayload(BaseModel):
    """Data sent to the client when a challenge is triggered."""
    challenge_id: str
    challenge_type: ChallengeLevel  # soft | hard
    question: str | None = None       # for soft challenge
    methods: list[str] = []           # for hard: ["secret_word", "voice_match"]
    timeout_seconds: int = 60


class ChallengeResponse(BaseModel):
    """Client's answer to a challenge."""
    challenge_id: str
    answer: str | None = None         # for soft challenge
    method: str | None = None         # for hard: "secret_word" or "voice_match"
    value: str | None = None          # for hard: the secret word value


class ChallengeResult(BaseModel):
    """Result of evaluating a challenge response."""
    passed: bool
    message: str
    new_score: int


# ─── WebSocket message types ────────────────────────────────


class WSChallenge(BaseModel):
    type: str = "challenge"
    challenge_id: str
    challenge_type: str   # "soft" | "hard"
    question: str | None = None
    methods: list[str] = []
    timeout_seconds: int = 60


class WSChallengeResult(BaseModel):
    type: str = "challenge_result"
    passed: bool
    message: str


class WSLockout(BaseModel):
    type: str = "lockout"
    message: str = "Session locked due to suspicious activity. Please re-authenticate."
