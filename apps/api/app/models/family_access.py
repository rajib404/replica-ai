from datetime import datetime

from pydantic import BaseModel, Field

# ─── Topic / Time restrictions ───────────────────────────


class TopicRestrictions(BaseModel):
    allowed: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


class TimeRestrictions(BaseModel):
    days: list[str] = Field(
        default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    )
    start_hour: int = Field(default=0, ge=0, le=23)
    end_hour: int = Field(default=23, ge=0, le=23)
    timezone: str = "UTC"


# ─── Access Rule Requests ────────────────────────────────


class CreateAccessRuleRequest(BaseModel):
    grantee_name: str = Field(default="", max_length=100)
    grantee_relation: str | None = Field(
        default=None,
        pattern="^(son|daughter|grandson|granddaughter|spouse|sibling|parent|grandparent|friend|custom)$",
    )
    access_level: str = Field(default="limited", pattern="^(full|read_only|limited)$")
    verification_method: str = Field(
        default="none",
        pattern="^(secret_word|secret_event|voice_match|face_match|none)$",
    )
    verification_value: str | None = Field(default=None, min_length=1, max_length=200)
    topic_restrictions: TopicRestrictions | None = None
    time_restrictions: TimeRestrictions | None = None
    allowed_content_types: list[str] | None = None
    allowed_information_categories: list[str] | None = None
    valid_until: datetime | None = None
    template_name: str | None = None


class UpdateAccessRuleRequest(BaseModel):
    grantee_name: str | None = Field(default=None, min_length=1, max_length=100)
    grantee_relation: str | None = None
    access_level: str | None = Field(default=None, pattern="^(full|read_only|limited)$")
    verification_method: str | None = Field(
        default=None,
        pattern="^(secret_word|secret_event|voice_match|face_match|none)$",
    )
    verification_value: str | None = None
    topic_restrictions: TopicRestrictions | None = None
    time_restrictions: TimeRestrictions | None = None
    allowed_content_types: list[str] | None = None
    allowed_information_categories: list[str] | None = None
    is_active: bool | None = None
    valid_until: datetime | None = None


# ─── Access Rule Responses ───────────────────────────────


class AccessRuleResponse(BaseModel):
    id: str
    owner_id: str
    grantee_name: str
    grantee_relation: str | None = None
    access_level: str
    verification_method: str
    is_active: bool
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    topic_restrictions: dict | None = None
    time_restrictions: dict | None = None
    allowed_content_types: list[str] | None = None
    allowed_information_categories: list[str] | None = None
    template_name: str | None = None
    created_at: datetime
    updated_at: datetime


class AccessRuleListResponse(BaseModel):
    rules: list[AccessRuleResponse]
    total: int


# ─── Invite ──────────────────────────────────────────────


class GenerateInviteRequest(BaseModel):
    is_reusable: bool = False
    max_uses: int = Field(default=1, ge=1, le=100)


class InviteResponse(BaseModel):
    invite_id: str
    invite_url: str
    invite_token: str
    qr_code_base64: str
    is_reusable: bool
    uses_remaining: int
    expires_at: datetime


# ─── Verification ────────────────────────────────────────


class FamilyVerifyRequest(BaseModel):
    invite_token: str
    verification_value: str | None = None


class FamilySessionResponse(BaseModel):
    verified: bool
    message: str
    session_token: str | None = None
    access_level: str | None = None
    grantee_name: str | None = None
    topic_restrictions: dict | None = None
    time_restrictions: dict | None = None


# ─── Family Code (durable, non-expiring global entry point) ─

class FamilyCodeResponse(BaseModel):
    family_code: str


class FamilyLoginRequest(BaseModel):
    family_code: str = Field(min_length=4, max_length=32)
    grantee_name: str = Field(min_length=1, max_length=100)
    verification_value: str = Field(min_length=1, max_length=200)


# ─── Templates ───────────────────────────────────────────


class AccessTemplateResponse(BaseModel):
    name: str
    label: str
    description: str
    config: CreateAccessRuleRequest


class TemplateListResponse(BaseModel):
    templates: list[AccessTemplateResponse]


# ─── Legacy Mode ─────────────────────────────────────────


class LegacyConfigureRequest(BaseModel):
    trigger_type: str = Field(pattern="^(manual|inactivity|trusted_person)$")
    inactivity_days: int = Field(default=365, ge=30, le=3650)
    trusted_person_rule_id: str | None = None


class LegacyConfigResponse(BaseModel):
    id: str
    owner_id: str
    trigger_type: str
    inactivity_days: int
    trusted_person_rule_id: str | None = None
    is_active: bool
    activated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LegacyActivateResponse(BaseModel):
    activated: bool
    message: str
    activated_at: datetime | None = None
