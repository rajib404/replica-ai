from datetime import datetime

from pydantic import BaseModel, Field


# ─── Requests ────────────────────────────────────────────


class CreateExternalLLMConfigRequest(BaseModel):
    provider: str = Field(..., pattern="^(openai|anthropic|google|custom)$")
    api_key: str = Field(..., min_length=1)
    model_name: str | None = None
    monthly_budget_usd: float = Field(default=0.0, ge=0)
    daily_budget_usd: float = Field(default=0.0, ge=0)
    auto_learn: bool = False


class UpdateExternalLLMConfigRequest(BaseModel):
    model_name: str | None = None
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    daily_budget_usd: float | None = Field(default=None, ge=0)
    is_active: bool | None = None
    auto_learn: bool | None = None
    api_key: str | None = Field(default=None, min_length=1)


class ExternalQueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50_000)
    config_id: str | None = None
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0, le=2)
    learn: bool | None = None  # override auto_learn per request


# ─── Responses ───────────────────────────────────────────


class ExternalLLMConfigResponse(BaseModel):
    id: str
    owner_id: str
    provider: str
    model_name: str | None = None
    monthly_budget_usd: float
    daily_budget_usd: float
    spent_this_month_usd: float
    is_active: bool
    auto_learn: bool
    created_at: datetime
    updated_at: datetime


class ExternalLLMConfigListResponse(BaseModel):
    configs: list[ExternalLLMConfigResponse]
    total: int


class ExternalQueryResponse(BaseModel):
    response: str
    provider: str
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    was_sanitized: bool = False
    learned: bool = False
    budget_warning: str | None = None


class UsageLogEntry(BaseModel):
    id: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    was_sanitized: bool
    created_at: datetime


class UsageSummary(BaseModel):
    total_cost_usd: float
    total_queries: int
    total_prompt_tokens: int
    total_completion_tokens: int
    budget_remaining_monthly: float
    budget_pct_used: float
    logs: list[UsageLogEntry]


class BudgetAlertResponse(BaseModel):
    alert: bool
    pct_used: float
    monthly_budget_usd: float
    spent_this_month_usd: float
    message: str
