"""Pydantic models and SQLAlchemy model for voice chat."""

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.owner import Base, _utcnow


# ─── SQLAlchemy ───────────────────────────────────────────


class VoiceSettings(Base):
    __tablename__ = "voice_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    voice_id: Mapped[str] = mapped_column(String, nullable=False, default="en_US-lessac-medium")
    speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    auto_play: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    output_format: Mapped[str] = mapped_column(String, nullable=False, default="mp3")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


# ─── WebSocket message types ─────────────────────────────


class WSVoiceAuth(BaseModel):
    type: str = "auth"
    token: str


class WSVoiceAudioIn(BaseModel):
    """Client sends audio chunk as binary, preceded by a JSON control message."""
    type: str = "audio"
    format: str = "webm"  # webm, wav, mp3, ogg
    sample_rate: int = 16000
    is_final: bool = False  # True = end of utterance (push-to-talk release)


class WSVoiceTranscript(BaseModel):
    """Server sends partial or final transcription."""
    type: str = "transcript"
    text: str
    is_final: bool = False
    confidence: float = 0.0


class WSVoiceAudioOut(BaseModel):
    """Server sends TTS audio metadata (actual audio follows as binary frame)."""
    type: str = "audio_out"
    format: str = "mp3"
    sample_rate: int = 22050
    duration_ms: int = 0
    text: str = ""  # the text that was spoken


class WSVoiceResponseText(BaseModel):
    """Server sends the LLM response text before TTS audio."""
    type: str = "response_text"
    text: str
    message_id: str
    thread_id: str
    sources: list[dict] = Field(default_factory=list)
    is_learning: bool = False


class WSVoiceDone(BaseModel):
    """Server signals voice exchange is complete."""
    type: str = "done"
    message_id: str
    thread_id: str


class WSVoiceError(BaseModel):
    type: str = "error"
    detail: str


class WSVoiceStatus(BaseModel):
    """Server sends status updates during processing."""
    type: str = "status"
    status: str  # "listening", "transcribing", "thinking", "speaking"


# ─── REST request/response models ────────────────────────


class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    language: str
    gender: str | None = None
    description: str | None = None


class VoiceListResponse(BaseModel):
    voices: list[VoiceInfo]


class VoiceSettingsResponse(BaseModel):
    voice_id: str
    speed: float
    auto_play: bool
    output_format: str


class UpdateVoiceSettingsRequest(BaseModel):
    voice_id: str | None = None
    speed: float | None = Field(None, ge=0.5, le=2.0)
    auto_play: bool | None = None
    output_format: str | None = Field(None, pattern=r"^(mp3|wav)$")
