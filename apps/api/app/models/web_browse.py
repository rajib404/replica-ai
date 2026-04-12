from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


# ─── Requests ────────────────────────────────────────────


class BrowseUrlRequest(BaseModel):
    url: str = Field(..., min_length=1)
    summarize: bool = True


class SearchWebRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=10, ge=1, le=20)
    summarize_top: int = Field(default=0, ge=0, le=5)


class CreateMonitorRequest(BaseModel):
    url: str = Field(..., min_length=1)
    keywords: list[str] = Field(default_factory=list)
    interval_hours: float = Field(default=24.0, ge=0.5, le=720)


class UpdateMonitorRequest(BaseModel):
    keywords: list[str] | None = None
    interval_hours: float | None = Field(default=None, ge=0.5, le=720)
    status: str | None = Field(default=None, pattern="^(active|paused)$")


class CreateDomainRuleRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=255)
    rule_type: str = Field(..., pattern="^(allow|block)$")


class UpdateBrowseConfigRequest(BaseModel):
    enabled: bool | None = None
    auto_summarize: bool | None = None
    max_pages_per_day: int | None = Field(default=None, ge=1, le=500)


# ─── Responses ───────────────────────────────────────────


class BrowseResult(BaseModel):
    id: str
    url: str
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    status_code: int | None = None
    content_length: int = 0
    fetch_ms: int = 0
    error: str | None = None


class SearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str
    summary: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class MonitorResponse(BaseModel):
    id: str
    url: str
    keywords: list[str]
    interval_hours: float
    status: str
    last_checked_at: datetime | None = None
    last_triggered_at: datetime | None = None
    trigger_reason: str | None = None
    check_count: int = 0
    created_at: datetime


class MonitorListResponse(BaseModel):
    monitors: list[MonitorResponse]
    total: int


class BrowseLogEntry(BaseModel):
    id: str
    url: str
    title: str | None = None
    summary: str | None = None
    status_code: int | None = None
    content_length: int = 0
    fetch_ms: int = 0
    error: str | None = None
    created_at: datetime


class BrowseHistoryResponse(BaseModel):
    logs: list[BrowseLogEntry]
    total: int


class DomainRuleResponse(BaseModel):
    id: str
    domain: str
    rule_type: str
    created_at: datetime


class DomainRuleListResponse(BaseModel):
    rules: list[DomainRuleResponse]
    total: int


class BrowseConfigResponse(BaseModel):
    enabled: bool
    auto_summarize: bool
    max_pages_per_day: int
