"""Pydantic models for the self-learning system."""

from pydantic import BaseModel, Field


# ─── Knowledge Gaps ──────────────────────────────────────

class KnowledgeGap(BaseModel):
    topic: str
    reason: str
    priority: str = "medium"  # low, medium, high
    suggested_queries: list[str] = []


class KnowledgeGapsResponse(BaseModel):
    gaps: list[KnowledgeGap]
    total_entries: int
    last_analysis_at: str | None = None


# ─── Learn Topic ─────────────────────────────────────────

class LearnTopicRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    depth: str = Field(default="moderate", pattern=r"^(shallow|moderate|deep)$")


class LearnTopicSource(BaseModel):
    url: str | None = None
    title: str | None = None
    type: str  # "web_search", "rag", "external_llm"


class LearnTopicResponse(BaseModel):
    topic: str
    depth: str
    sources_used: list[LearnTopicSource]
    entries_created: int
    summary: str


# ─── Learning Report ─────────────────────────────────────

class LearningReportEntry(BaseModel):
    id: str
    topic: str
    depth: str
    sources_used: list[LearnTopicSource]
    entries_created: int
    summary: str | None = None
    status: str
    error_message: str | None = None
    created_at: str


class LearningReportResponse(BaseModel):
    entries: list[LearningReportEntry]
    total: int
    page: int
    page_size: int


# ─── Learning Preferences ───────────────────────────────

class LearningPreferences(BaseModel):
    enabled: bool = False
    auto_topics: list[str] = []
    ignore_topics: list[str] = []
    depth: str = Field(default="moderate", pattern=r"^(shallow|moderate|deep)$")
    schedule_hour_utc: int = Field(default=3, ge=0, le=23)
    max_daily_web_searches: int = Field(default=10, ge=0, le=50)
    use_external_llm: bool = False


class LearningPreferencesResponse(BaseModel):
    preferences: LearningPreferences
    owner_id: str


# ─── Knowledge Maintenance ──────────────────────────────

class StaleKnowledgeEntry(BaseModel):
    entry_id: str
    content_type: str
    age_days: int
    relevance_score: float | None = None


class StaleKnowledgeResponse(BaseModel):
    stale_entries: list[StaleKnowledgeEntry]
    total_entries: int
    threshold_days: int


class ConsolidationResult(BaseModel):
    groups_found: int
    entries_consolidated: int
    new_entries_created: int
    summary: str
