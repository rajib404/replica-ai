from pydantic import BaseModel, Field

# ─── Setup ────────────────────────────────────────────────

class SetupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    phone: str | None = None
    preferred_language: str = Field(default="en", max_length=10)
    password: str | None = Field(default=None, min_length=8, max_length=200)
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


# ─── Login ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    verification_type: str = Field(
        default="password", pattern="^(password|secret_word|secret_event)$"
    )
    value: str = Field(min_length=1)


class LoginResponse(BaseModel):
    verified: bool
    message: str
    owner_id: str | None = None
    tokens: TokenPair | None = None


# ─── Profile ──────────────────────────────────────────────

class ProfileResponse(BaseModel):
    owner_id: str
    name: str
    email: str
    phone: str | None = None
    preferred_language: str
    has_password: bool
    google_linked: bool


class UpdateProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    phone: str | None = None


# ─── Password management ───────────────────────────────────

class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)
    current_password: str | None = Field(default=None, min_length=1)


class SetPasswordResponse(BaseModel):
    success: bool
    message: str


# ─── Logout ─────────────────────────────────────────────────

class LogoutRequest(BaseModel):
    refresh_token: str


class LogoutResponse(BaseModel):
    success: bool


# ─── Refresh ─────────────────────────────────────────────

class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    tokens: TokenPair
