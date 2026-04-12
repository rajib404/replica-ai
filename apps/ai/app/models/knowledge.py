from pydantic import BaseModel, Field


class TextIngestRequest(BaseModel):
    owner_id: str
    text: str = Field(..., min_length=1, max_length=100_000)
    language: str | None = None
    english_translation: str | None = None  # pre-translated by LanguageEngine


class IngestResult(BaseModel):
    """Result returned after successful ingestion (caller writes to DB)."""
    entry_id: str
    language: str
    english_translation: str | None = None
    embedding_id: str | None = None
    content_preview: str | None = None
    original_content_path: str | None = None
    metadata: dict | None = None


class AudioIngestRequest(BaseModel):
    owner_id: str


class VideoIngestRequest(BaseModel):
    owner_id: str


class DocumentIngestRequest(BaseModel):
    owner_id: str


class IngestAcceptedResponse(BaseModel):
    task_id: str
    status: str = "pending"


class TaskStatusResponse(BaseModel):
    task_id: str
    owner_id: str
    status: str
    progress: int = 0
    result: dict | None = None
    error: str | None = None
    created_at: str
    updated_at: str
