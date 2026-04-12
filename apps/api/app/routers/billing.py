"""Billing & hosting endpoints: Stripe setup, subscriptions, payments, survival config."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import require_role
from app.core.database import get_db
from app.models.billing import (
    BillingStatusResponse,
    CancelSubscriptionRequest,
    CostBreakdownResponse,
    HostingStatusResponse,
    PaymentHistoryResponse,
    PaymentLogResponse,
    SetupBillingRequest,
    SetupBillingResponse,
    SubscribeResponse,
    SurvivalConfigResponse,
    UpdateAutoPayRequest,
    UpdateSurvivalConfigRequest,
)
from app.services.self_manager import HostingManager, SelfPreservation

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ─── Billing Setup ──────────────────────────────────────


@router.post("/setup", response_model=SetupBillingResponse)
async def setup_billing(
    body: SetupBillingRequest,
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Create or update Stripe customer with a payment method."""
    try:
        result = await HostingManager.setup_billing(
            owner_id=owner["sub"],
            payment_method_id=body.payment_method_id,
            db=db,
        )
        return SetupBillingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe subscription for hosting."""
    try:
        result = await HostingManager.subscribe(
            owner_id=owner["sub"], db=db
        )
        return SubscribeResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ─── Status ─────────────────────────────────────────────


@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Get current billing and payment status."""
    config = await HostingManager.ensure_billing_config(owner["sub"], db)
    hosting = await HostingManager.check_hosting_status(owner["sub"], db)
    return BillingStatusResponse(
        has_payment_method=config.stripe_customer_id is not None,
        card_last_four=config.card_last_four,
        card_brand=config.card_brand,
        auto_pay_hosting=config.auto_pay_hosting,
        auto_pay_llm=config.auto_pay_llm,
        stripe_customer_id=config.stripe_customer_id,
        stripe_subscription_id=config.stripe_subscription_id,
        hosting_expires_at=config.hosting_expires_at,
        days_until_expiry=hosting["days_until_expiry"],
        survival_mode=config.survival_mode,
        survival_mode_entered_at=config.survival_mode_entered_at,
        last_payment_at=config.last_payment_at,
    )


@router.get("/hosting", response_model=HostingStatusResponse)
async def get_hosting_status(
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Get hosting status summary."""
    result = await HostingManager.check_hosting_status(owner["sub"], db)
    return HostingStatusResponse(**result)


# ─── Cancel ─────────────────────────────────────────────


@router.post("/cancel")
async def cancel_subscription(
    body: CancelSubscriptionRequest,
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Cancel the hosting subscription (keeps access until period end)."""
    try:
        result = await HostingManager.cancel_subscription(owner["sub"], db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ─── Auto-pay ───────────────────────────────────────────


@router.put("/auto-pay")
async def update_auto_pay(
    body: UpdateAutoPayRequest,
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Toggle auto-pay for hosting and/or LLM."""
    config = await HostingManager.update_auto_pay(
        owner_id=owner["sub"],
        auto_pay_hosting=body.auto_pay_hosting,
        auto_pay_llm=body.auto_pay_llm,
        db=db,
    )
    return {
        "auto_pay_hosting": config.auto_pay_hosting,
        "auto_pay_llm": config.auto_pay_llm,
    }


# ─── Payment History ────────────────────────────────────


@router.get("/payments", response_model=PaymentHistoryResponse)
async def get_payment_history(
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Get payment log history."""
    result = await HostingManager.get_payment_history(owner["sub"], db)
    payments = [
        PaymentLogResponse(
            id=p.id,
            amount_usd=p.amount_usd,
            currency=p.currency,
            description=p.description,
            status=p.status.value if hasattr(p.status, "value") else p.status,
            error_message=p.error_message,
            created_at=p.created_at,
        )
        for p in result["payments"]
    ]
    return PaymentHistoryResponse(payments=payments, total=result["total"])


# ─── Cost Breakdown ─────────────────────────────────────


@router.get("/costs", response_model=CostBreakdownResponse)
async def get_cost_breakdown(
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Get monthly cost breakdown with projections and suggestions."""
    result = await HostingManager.get_cost_breakdown(owner["sub"], db)
    return CostBreakdownResponse(**result)


# ─── Survival Config ────────────────────────────────────


@router.get("/survival", response_model=SurvivalConfigResponse)
async def get_survival_config(
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Get self-preservation / survival configuration."""
    config = await SelfPreservation.get_survival_config(owner["sub"], db)
    return SurvivalConfigResponse(
        grace_period_days=config.grace_period_days,
        notify_family=config.notify_family,
        weekly_reminders=config.weekly_reminders,
        never_shutdown_with_family=config.never_shutdown_with_family,
    )


@router.put("/survival", response_model=SurvivalConfigResponse)
async def update_survival_config(
    body: UpdateSurvivalConfigRequest,
    owner=Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    """Update self-preservation / survival configuration."""
    config = await SelfPreservation.update_survival_config(
        owner_id=owner["sub"],
        updates=body.model_dump(exclude_none=True),
        db=db,
    )
    return SurvivalConfigResponse(
        grace_period_days=config.grace_period_days,
        notify_family=config.notify_family,
        weekly_reminders=config.weekly_reminders,
        never_shutdown_with_family=config.never_shutdown_with_family,
    )


# ─── Stripe Webhook ─────────────────────────────────────


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events (no auth — verified by signature)."""
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    payload = await request.body()
    try:
        result = await HostingManager.handle_stripe_webhook(
            payload=payload, sig_header=stripe_signature, db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
