"""Pydantic models for Web Push notifications."""

from datetime import datetime

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    """Encryption keys returned by the browser PushManager."""

    p256dh: str = Field(..., description="ECDH public key (base64url)")
    auth: str = Field(..., description="Shared auth secret (base64url)")


class PushSubscriptionCreate(BaseModel):
    """Payload posted by the PWA client to register a push subscription."""

    endpoint: str = Field(..., description="Push service endpoint URL")
    keys: PushKeys
    user_agent: str | None = Field(None, alias="userAgent")

    model_config = {"populate_by_name": True}


class PushSubscriptionResponse(BaseModel):
    id: str
    endpoint: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class PushTestRequest(BaseModel):
    title: str = "Replica AI"
    body: str = "Test notification from Replica AI"
    url: str | None = "/dashboard/chat"


class PushVapidKeyResponse(BaseModel):
    key: str
