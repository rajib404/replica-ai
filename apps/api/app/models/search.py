from datetime import datetime

from pydantic import BaseModel, Field

from app.models.knowledge import ContentType


# ─── Request schemas ─────────────────────────────────────


class DateRange(BaseModel):
    start: datetime
    end: datetime


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    top_k: int = Field(default=5, ge=1, le=50)
    content_type: ContentType | None = None
    date_range: DateRange | None = None


# ─── Response schemas ────────────────────────────────────


class SearchResultItem(BaseModel):
    entry_id: str
    content_type: str
    score: float
    content_preview: str | None = None
    original_language: str | None = None
    metadata: dict | None = None
    created_at: datetime | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class RAGSourceEntry(BaseModel):
    entry_id: str
    content_type: str
    score: float


class RAGResponse(BaseModel):
    response: str
    sources: list[RAGSourceEntry]
    query_used: str
