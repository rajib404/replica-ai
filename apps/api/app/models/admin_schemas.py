"""Pydantic request/response models for the admin dashboard."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─── Auth ────────────────────────────────────────────────


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=512)


class AdminLoginResponse(BaseModel):
    access_token: str
    expires_at: datetime


class AdminSessionResponse(BaseModel):
    username: str
    expires_at: datetime | None = None


# ─── Overview ────────────────────────────────────────────


class SystemResources(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    disk_percent: float
    disk_used_bytes: int
    disk_total_bytes: int


class SystemOverviewResponse(BaseModel):
    owner_count: int
    knowledge_count: int
    active_instance_count: int
    message_count: int
    thread_count: int
    approximate_storage_bytes: int
    resources: SystemResources
    uptime_seconds: float


# ─── Owners ──────────────────────────────────────────────


class OwnerSummary(BaseModel):
    id: str
    name: str
    email: str
    instance_count: int
    knowledge_count: int
    message_count: int
    last_active_at: datetime | None = None
    created_at: datetime


class OwnerListResponse(BaseModel):
    items: list[OwnerSummary]
    total: int
    page: int
    page_size: int


class OwnerDetailResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None = None
    preferred_language: str
    instance_count: int
    knowledge_count: int
    message_count: int
    thread_count: int
    last_active_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ─── Health ──────────────────────────────────────────────


class ServiceHealthEntry(BaseModel):
    name: str
    status: str  # healthy | degraded | down
    response_time_ms: float | None = None
    last_error: str | None = None
    checked_at: datetime
    details: dict[str, Any] | None = None


class HealthSnapshotResponse(BaseModel):
    items: list[ServiceHealthEntry]


# ─── Logs ────────────────────────────────────────────────


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    logger_name: str
    message: str
    exc_info: str | None = None


class LogsResponse(BaseModel):
    items: list[LogEntry]
    total: int
    capacity: int


# ─── System rules + config ───────────────────────────────


class RateLimitConfig(BaseModel):
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None


class SystemRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    personality_baseline: dict[str, Any] | None = None
    rate_limits: RateLimitConfig | None = None
    file_size_limit_bytes: int | None = None
    base_model: str | None = None
    is_default: bool = False


class SystemRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    personality_baseline: dict[str, Any] | None = None
    rate_limits: RateLimitConfig | None = None
    file_size_limit_bytes: int | None = None
    base_model: str | None = None
    is_default: bool | None = None


class SystemRuleResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    system_prompt: str | None = None
    personality_baseline: dict[str, Any] | None = None
    rate_limits: dict[str, Any] | None = None
    file_size_limit_bytes: int | None = None
    base_model: str | None = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class SystemConfigUpdate(BaseModel):
    default_rule_id: str | None = None
    default_base_model: str | None = None
    global_rate_limit_per_minute: int | None = None
    global_file_size_limit_bytes: int | None = None
    maintenance_mode: bool | None = None


class SystemConfigResponse(BaseModel):
    id: str
    default_rule_id: str | None = None
    default_base_model: str | None = None
    global_rate_limit_per_minute: int | None = None
    global_file_size_limit_bytes: int | None = None
    maintenance_mode: bool
    updated_at: datetime


# ─── Maintenance ─────────────────────────────────────────


class MaintenanceJobResponse(BaseModel):
    id: str
    job_type: str
    target: str | None = None
    status: str
    result: dict[str, Any] | None = None
    error_message: str | None = None
    started_by: str
    started_at: datetime
    completed_at: datetime | None = None


class MaintenanceJobListResponse(BaseModel):
    items: list[MaintenanceJobResponse]


class ClearCacheRequest(BaseModel):
    pattern: str | None = None


class RestartServiceRequest(BaseModel):
    service: str = Field(..., min_length=1, max_length=64)


class BroadcastRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1, max_length=2000)
    severity: str = Field(default="info")  # info | warning | critical
    expires_at: datetime | None = None
    send_push: bool = False


class BroadcastResponse(BaseModel):
    id: str
    title: str
    body: str
    severity: str
    push_sent: bool
    push_count: int
    created_by: str
    created_at: datetime
    expires_at: datetime | None = None
    active: bool


class BroadcastListResponse(BaseModel):
    items: list[BroadcastResponse]


# ─── Analytics ───────────────────────────────────────────


class TimeSeriesPoint(BaseModel):
    date: str  # ISO date string
    value: float


class TimeSeriesResponse(BaseModel):
    points: list[TimeSeriesPoint]


class KnowledgeTypeBucket(BaseModel):
    content_type: str
    count: int


class KnowledgeTypeResponse(BaseModel):
    items: list[KnowledgeTypeBucket]


class ExternalLLMUsagePoint(BaseModel):
    date: str
    provider: str
    cost_usd: float
    tokens: int


class ExternalLLMUsageResponse(BaseModel):
    items: list[ExternalLLMUsagePoint]


class StorageProjectionPoint(BaseModel):
    date: str
    value: float
    projected: bool = False


class StorageProjectionResponse(BaseModel):
    points: list[StorageProjectionPoint]
