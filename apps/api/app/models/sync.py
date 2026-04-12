from datetime import datetime

from pydantic import BaseModel, Field


# ─── Requests ────────────────────────────────────────────


class StartSyncRequest(BaseModel):
    source_instance_id: str
    target_instance_id: str
    sync_type: str = Field(default="full", pattern="^(full|incremental|model_weights)$")
    since: datetime | None = None  # required for incremental


class ResolveConflictRequest(BaseModel):
    resolution: str = Field(pattern="^(keep_source|keep_target|keep_both)$")


# ─── Responses ───────────────────────────────────────────


class SyncConflictResponse(BaseModel):
    id: str
    sync_log_id: str
    entry_id: str
    entry_type: str
    source_data: dict
    target_data: dict
    resolution: str
    resolved_at: datetime | None = None
    created_at: datetime


class SyncLogResponse(BaseModel):
    id: str
    source_instance_id: str
    target_instance_id: str
    sync_type: str
    entries_synced: int
    total_entries: int
    bytes_transferred: int
    total_bytes: int
    status: str
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    conflicts: list[SyncConflictResponse] = []


class SyncStartedResponse(BaseModel):
    sync_id: str
    status: str
    message: str


class SyncStatusResponse(BaseModel):
    sync: SyncLogResponse
    conflicts: list[SyncConflictResponse] = []


class SyncHistoryResponse(BaseModel):
    syncs: list[SyncLogResponse]
    total: int


class SyncProgressResponse(BaseModel):
    sync_id: str
    status: str
    entries_synced: int
    total_entries: int
    bytes_transferred: int
    total_bytes: int
    percent_complete: float
