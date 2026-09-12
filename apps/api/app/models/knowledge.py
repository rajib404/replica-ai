import enum
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.owner import Base, _utcnow

# ─── SQLAlchemy ──────────────────────────────────────────


class ContentType(str, enum.Enum):
    text = "text"
    audio = "audio"
    video = "video"
    image = "image"
    document = "document"


class InformationCategory(str, enum.Enum):
    memories_stories = "memories_stories"
    photos_videos = "photos_videos"
    voice_recordings = "voice_recordings"
    health_medical = "health_medical"
    financial = "financial"
    legal_official = "legal_official"
    relationships_family = "relationships_family"
    career_work = "career_work"
    beliefs_values = "beliefs_values"
    traditions_recipes = "traditions_recipes"
    advice_wisdom = "advice_wisdom"
    general = "general"


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, name="ContentType", create_type=False), nullable=False
    )
    original_content_path: Mapped[str | None] = mapped_column(String, nullable=True)
    original_language: Mapped[str | None] = mapped_column(String, nullable=True)
    english_translation: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_id: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[InformationCategory | None] = mapped_column(
        Enum(InformationCategory, name="InformationCategory", create_type=False),
        nullable=True,
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )


# ─── Pydantic Schemas ───────────────────────────────────


class TextIngestRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    language: str | None = None


class IngestCompletedResponse(BaseModel):
    entry_id: str
    status: str = "completed"


class IngestAcceptedResponse(BaseModel):
    task_id: str
    status: str = "pending"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    result: dict | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class KnowledgeEntryResponse(BaseModel):
    id: str
    owner_id: str
    content_type: str
    original_content_path: str | None = None
    original_language: str | None = None
    english_translation: str | None = None
    embedding_id: str | None = None
    category: str | None = None
    metadata_: dict | None = Field(None, serialization_alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class KnowledgeListResponse(BaseModel):
    entries: list[KnowledgeEntryResponse]
    total: int
    page: int
    page_size: int
