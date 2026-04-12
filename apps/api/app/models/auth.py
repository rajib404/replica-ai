from pydantic import BaseModel, Field


# ─── Setup ────────────────────────────────────────────────

class SetupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    phone: str | None = None
    preferred_language: str = Field(default="en", max_length=10)
    secret_word: str | None = Field(default=None, min_length=3, max_length=100)
    secret_event: str | None = Field(default=None, min_length=3, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SetupResponse(BaseModel):
    owner_id: str
    tokens: TokenPair
    connect_url: str
    qr_code_base64: str


# ─── Connect ──────────────────────────────────────────────

class ConnectRequest(BaseModel):
    token: str
    hostname: str = Field(min_length=1, max_length=200)
    instance_type: str = Field(default="local", pattern="^(cloud|local)$")


class ConnectResponse(BaseModel):
    session_token: str
    owner_id: str
    instance_id: str
    token_type: str = "bearer"


# ─── Verify ───────────────────────────────────────────────

class VerifyRequest(BaseModel):
    owner_id: str
    verification_type: str = Field(
        pattern="^(secret_word|secret_event|voice_match|face_match)$"
    )
    value: str | None = Field(default=None, min_length=1)


class VerifyResponse(BaseModel):
    verified: bool
    message: str
    tokens: TokenPair | None = None


# ─── Refresh ─────────────────────────────────────────────

class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    tokens: TokenPair
