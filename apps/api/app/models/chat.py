import enum
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.owner import Base, _utcnow


# ─── SQLAlchemy ──────────────────────────────────────────


class ParticipantType(str, enum.Enum):
    owner = "owner"
    family_member = "family_member"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ConversationThread(Base):
    __tablename__ = "conversation_threads"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    participant_type: Mapped[ParticipantType] = mapped_column(
        Enum(ParticipantType, name="ParticipantType", create_type=False), nullable=False
    )
    participant_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="MessageRole", create_type=False), nullable=False
    )
    content_text: Mapped[str | None] = mapped_column(String, nullable=True)
    content_audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    content_video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


# ─── Pydantic Schemas ───────────────────────────────────


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=50_000)
    thread_id: str | None = None


class ChatMessageResponse(BaseModel):
    thread_id: str
    message_id: str
    response: str
    sources: list[dict] = []
    is_learning: bool = False


class ThreadResponse(BaseModel):
    id: str
    owner_id: str
    participant_type: str
    participant_name: str
    created_at: datetime
    last_message: str | None = None

    model_config = {"from_attributes": True}


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]
    total: int


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    role: str
    content_text: str | None = None
    language: str = "en"
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageHistoryResponse(BaseModel):
    messages: list[MessageResponse]
    thread_id: str
    has_more: bool = False


class WSAuthMessage(BaseModel):
    type: str = "auth"
    token: str


class WSChatMessage(BaseModel):
    type: str = "message"
    text: str
    thread_id: str | None = None


class WSResponseToken(BaseModel):
    type: str = "token"
    token: str
    message_id: str


class WSResponseDone(BaseModel):
    type: str = "done"
    message_id: str
    thread_id: str
    sources: list[dict] = []
    is_learning: bool = False
    content: str = ""  # full response text (fallback when streaming failed)


class WSError(BaseModel):
    type: str = "error"
    detail: str


class WSLearning(BaseModel):
    type: str = "learning"
    status: str = "ingesting"
