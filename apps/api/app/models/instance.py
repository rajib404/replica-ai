from datetime import datetime

from pydantic import BaseModel, Field


# ─── Requests ────────────────────────────────────────────

class RegisterInstanceRequest(BaseModel):
    instance_type: str = Field(pattern="^(cloud|local)$")
    hostname: str = Field(min_length=1, max_length=200)
    api_url: str | None = Field(default=None, max_length=500)
    capabilities: list[str] = Field(default_factory=lambda: ["generate", "embed", "ingest"])


class PromoteInstanceRequest(BaseModel):
    pass


# ─── Responses ───────────────────────────────────────────

class InstanceResponse(BaseModel):
    id: str
    owner_id: str
    instance_type: str
    hostname: str
    status: str
    version: str
    capabilities: list[str] | None = None
    is_primary: bool = False
    last_heartbeat_at: datetime | None = None
    api_url: str | None = None
    created_at: datetime


class InstanceRegisteredResponse(BaseModel):
    instance: InstanceResponse
    auth_token: str


class InstanceListResponse(BaseModel):
    instances: list[InstanceResponse]
    total: int


class HeartbeatResponse(BaseModel):
    status: str
    last_heartbeat_at: datetime
