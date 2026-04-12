import enum
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.owner import Base, _utcnow


# ─── SQLAlchemy ───────────────────────────────────────────


class VerificationLog(Base):
    __tablename__ = "verification_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    method: Mapped[str] = mapped_column(String, nullable=False)  # "voice_match"
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="api")  # "api" | "passive"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


# ─── Pydantic schemas ────────────────────────────────────


class VoiceEnrollRequest(BaseModel):
    """Multipart upload — schema used for documentation only."""
    pass


class VoiceEnrollResponse(BaseModel):
    status: str  # "enrolled" | "needs_more_samples"
    samples_received: int
    samples_required: int
    message: str


class VoiceCheckResponse(BaseModel):
    verified: bool
    similarity_score: float
    threshold: float
    message: str


class VoiceStatusResponse(BaseModel):
    enrolled: bool
    samples_stored: int
    samples_required: int


class VerificationResult(BaseModel):
    verified: bool
    similarity_score: float
    threshold: float
