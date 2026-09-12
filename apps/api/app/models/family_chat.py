from datetime import datetime

from pydantic import BaseModel, Field

from app.models.knowledge import KnowledgeEntryResponse

# ─── Family Chat Requests ────────────────────────────────


class FamilyChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=50_000)
    thread_id: str | None = None


# ─── Family Chat Responses ───────────────────────────────


class FamilyChatMessageResponse(BaseModel):
    thread_id: str
    message_id: str
    response: str
    sources: list[dict] = []


class FamilySessionInfoResponse(BaseModel):
    owner_id: str
    owner_name: str
    grantee_name: str
    access_level: str
    topic_restrictions: dict | None = None
    time_restrictions: dict | None = None
    legacy_mode_active: bool = False


# ─── Notification / Monitoring ──────���────────────────────


class FamilySessionSummary(BaseModel):
    thread_id: str
    grantee_name: str
    grantee_relation: str | None = None
    access_level: str
    message_count: int = 0
    last_message_at: datetime | None = None
    started_at: datetime


class ActiveSessionsResponse(BaseModel):
    sessions: list[FamilySessionSummary]
    total: int


class ConversationLogMessage(BaseModel):
    id: str
    role: str
    content_text: str | None = None
    language: str = "en"
    created_at: datetime


class ConversationLogResponse(BaseModel):
    thread_id: str
    grantee_name: str
    messages: list[ConversationLogMessage]
    has_more: bool = False


class InterveneSendRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=50_000)


class InterveneResponse(BaseModel):
    message_id: str
    thread_id: str
    sent: bool = True


# ─── Analytics ───────────────────────────────────────────


class FamilyMemberAnalytics(BaseModel):
    grantee_name: str
    grantee_relation: str | None = None
    total_sessions: int = 0
    total_messages: int = 0
    last_visit_at: datetime | None = None
    top_topics: list[str] = []


class FamilyAnalyticsResponse(BaseModel):
    members: list[FamilyMemberAnalytics]
    total_family_messages: int = 0
    total_family_sessions: int = 0


# ─── Family Assets ───────────────────────────────────────


class FamilyAssetListResponse(BaseModel):
    entries: list[KnowledgeEntryResponse]
    total: int


# ─── WebSocket messages ──────────────────────────────────


class WSFamilyNotification(BaseModel):
    type: str = "family_session"
    event: str  # "started" | "message" | "ended"
    grantee_name: str
    thread_id: str
    detail: str | None = None
