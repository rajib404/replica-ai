from datetime import datetime

from pydantic import BaseModel, Field


# ─── Requests ────────────────────────────────────────────


class SetupBillingRequest(BaseModel):
    payment_method_id: str = Field(..., min_length=1)


class SubscribeRequest(BaseModel):
    pass  # uses existing payment method on Stripe customer


class CancelSubscriptionRequest(BaseModel):
    reason: str | None = None


class UpdateAutoPayRequest(BaseModel):
    auto_pay_hosting: bool | None = None
    auto_pay_llm: bool | None = None


class UpdateSurvivalConfigRequest(BaseModel):
    grace_period_days: int | None = Field(default=None, ge=7, le=365)
    notify_family: bool | None = None
    weekly_reminders: bool | None = None
    never_shutdown_with_family: bool | None = None


# ─── Responses ───────────────────────────────────────────


class BillingStatusResponse(BaseModel):
    has_payment_method: bool
    card_last_four: str | None = None
    card_brand: str | None = None
    auto_pay_hosting: bool
    auto_pay_llm: bool
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    hosting_expires_at: datetime | None = None
    days_until_expiry: int | None = None
    survival_mode: bool
    survival_mode_entered_at: datetime | None = None
    last_payment_at: datetime | None = None


class HostingStatusResponse(BaseModel):
    status: str  # active, expiring, expired, survival
    days_until_expiry: int | None = None
    monthly_cost: float
    is_auto_pay_active: bool
    survival_mode: bool
    survival_days_remaining: int | None = None


class PaymentLogResponse(BaseModel):
    id: str
    amount_usd: float
    currency: str
    description: str
    status: str
    error_message: str | None = None
    created_at: datetime


class PaymentHistoryResponse(BaseModel):
    payments: list[PaymentLogResponse]
    total: int


class CostBreakdownResponse(BaseModel):
    hosting_monthly_usd: float
    llm_monthly_usd: float
    storage_monthly_usd: float
    total_monthly_usd: float
    projected_annual_usd: float
    suggestions: list[str]


class SurvivalConfigResponse(BaseModel):
    grace_period_days: int
    notify_family: bool
    weekly_reminders: bool
    never_shutdown_with_family: bool


class SetupBillingResponse(BaseModel):
    stripe_customer_id: str
    card_last_four: str | None = None
    card_brand: str | None = None
    message: str


class SubscribeResponse(BaseModel):
    subscription_id: str
    status: str
    current_period_end: datetime | None = None
    message: str
