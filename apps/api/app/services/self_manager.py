"""Self-management service: hosting, billing, payments, survival mode, self-preservation."""

import logging
from datetime import UTC, datetime, timedelta

from cuid2 import cuid_wrapper
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.owner import (
    AccessRule,
    BillingConfig,
    BrowseConfig,
    ExternalLLMConfig,
    ExternalLLMUsageLog,
    LegacyConfig,
    Owner,
    PaymentLog,
    PaymentStatus,
    SurvivalConfig,
)

logger = logging.getLogger(__name__)
generate_cuid = cuid_wrapper()


# ─── HostingManager ──────────────────────────────────────


class HostingManager:
    """Manages hosting status, payments via Stripe, and survival mode."""

    # -- Billing config CRUD --

    @staticmethod
    async def get_billing_config(
        owner_id: str, db: AsyncSession
    ) -> BillingConfig | None:
        result = await db.execute(
            select(BillingConfig).where(BillingConfig.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def ensure_billing_config(
        owner_id: str, db: AsyncSession
    ) -> BillingConfig:
        config = await HostingManager.get_billing_config(owner_id, db)
        if not config:
            config = BillingConfig(
                id=generate_cuid(),
                owner_id=owner_id,
            )
            db.add(config)
            await db.commit()
            await db.refresh(config)
        return config

    # -- Hosting status --

    @staticmethod
    async def check_hosting_status(
        owner_id: str, db: AsyncSession
    ) -> dict:
        """Check hosting health, expiry, and payment status."""
        config = await HostingManager.ensure_billing_config(owner_id, db)
        now = datetime.now(UTC).replace(tzinfo=None)

        days_until_expiry: int | None = None
        if config.hosting_expires_at:
            delta = config.hosting_expires_at - now
            days_until_expiry = max(delta.days, 0)

        if config.survival_mode:
            status = "survival"
            survival_days_remaining = None
            survival_config = await SelfPreservation.get_survival_config(owner_id, db)
            if config.survival_mode_entered_at:
                elapsed = (now - config.survival_mode_entered_at).days
                survival_days_remaining = max(
                    survival_config.grace_period_days - elapsed, 0
                )
        elif days_until_expiry is not None and days_until_expiry <= 0:
            status = "expired"
        elif days_until_expiry is not None and days_until_expiry <= 7:
            status = "expiring"
        else:
            status = "active"

        return {
            "status": status,
            "days_until_expiry": days_until_expiry,
            "monthly_cost": settings.hosting_monthly_cost_usd,
            "is_auto_pay_active": config.auto_pay_hosting,
            "survival_mode": config.survival_mode,
            "survival_days_remaining": (
                survival_days_remaining if config.survival_mode else None
            ),
        }

    # -- Stripe setup --

    @staticmethod
    async def setup_billing(
        owner_id: str,
        payment_method_id: str,
        db: AsyncSession,
    ) -> dict:
        """Create or update Stripe customer with a payment method."""
        import stripe

        stripe.api_key = settings.stripe_secret_key
        config = await HostingManager.ensure_billing_config(owner_id, db)

        # Get owner info for Stripe customer
        owner_result = await db.execute(
            select(Owner).where(Owner.id == owner_id)
        )
        owner = owner_result.scalar_one()

        # Create or retrieve Stripe customer
        if config.stripe_customer_id:
            customer = stripe.Customer.modify(
                config.stripe_customer_id,
                name=owner.name,
                email=owner.email,
            )
        else:
            customer = stripe.Customer.create(
                name=owner.name,
                email=owner.email,
                metadata={"owner_id": owner_id},
            )
            config.stripe_customer_id = customer.id

        # Attach payment method
        stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer.id,
        )
        stripe.Customer.modify(
            customer.id,
            invoice_settings={"default_payment_method": payment_method_id},
        )

        # Get card details
        pm = stripe.PaymentMethod.retrieve(payment_method_id)
        card = pm.get("card", {})
        config.card_last_four = card.get("last4")
        config.card_brand = card.get("brand")

        await db.commit()
        await db.refresh(config)

        return {
            "stripe_customer_id": config.stripe_customer_id,
            "card_last_four": config.card_last_four,
            "card_brand": config.card_brand,
            "message": "Payment method added successfully.",
        }

    # -- Subscribe --

    @staticmethod
    async def subscribe(
        owner_id: str, db: AsyncSession
    ) -> dict:
        """Create a Stripe subscription for hosting."""
        import stripe

        stripe.api_key = settings.stripe_secret_key
        config = await HostingManager.ensure_billing_config(owner_id, db)

        if not config.stripe_customer_id:
            raise ValueError("No payment method on file. Set up billing first.")

        if config.stripe_subscription_id:
            # Retrieve existing
            sub = stripe.Subscription.retrieve(config.stripe_subscription_id)
            if sub.status in ("active", "trialing"):
                return {
                    "subscription_id": sub.id,
                    "status": sub.status,
                    "current_period_end": datetime.fromtimestamp(
                        sub.current_period_end, tz=UTC
                    ).replace(tzinfo=None),
                    "message": "Subscription already active.",
                }

        # Create subscription
        sub = stripe.Subscription.create(
            customer=config.stripe_customer_id,
            items=[{"price": settings.stripe_price_id}],
            metadata={"owner_id": owner_id},
        )

        config.stripe_subscription_id = sub.id
        config.auto_pay_hosting = True
        config.hosting_expires_at = datetime.fromtimestamp(
            sub.current_period_end, tz=UTC
        ).replace(tzinfo=None)

        # Exit survival mode if it was active
        if config.survival_mode:
            await HostingManager._exit_survival_mode(config, db)

        await db.commit()
        await db.refresh(config)

        return {
            "subscription_id": sub.id,
            "status": sub.status,
            "current_period_end": config.hosting_expires_at,
            "message": "Subscription created successfully.",
        }

    # -- Cancel subscription --

    @staticmethod
    async def cancel_subscription(
        owner_id: str, db: AsyncSession
    ) -> dict:
        """Cancel the Stripe subscription (keeps access until period end)."""
        import stripe

        stripe.api_key = settings.stripe_secret_key
        config = await HostingManager.ensure_billing_config(owner_id, db)

        if not config.stripe_subscription_id:
            raise ValueError("No active subscription to cancel.")

        stripe.Subscription.modify(
            config.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        config.auto_pay_hosting = False

        await db.commit()
        return {"message": "Subscription will cancel at end of current period."}

    # -- Payment processing --

    @staticmethod
    async def renew_hosting(
        owner_id: str, db: AsyncSession
    ) -> dict:
        """Attempt to process a hosting payment (one-time charge if no subscription)."""
        import stripe

        stripe.api_key = settings.stripe_secret_key
        config = await HostingManager.ensure_billing_config(owner_id, db)

        if not config.stripe_customer_id:
            raise ValueError("No payment method on file.")
        if not config.auto_pay_hosting:
            raise ValueError("Auto-pay is disabled.")

        amount_cents = int(settings.hosting_monthly_cost_usd * 100)
        log_id = generate_cuid()

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                customer=config.stripe_customer_id,
                confirm=True,
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
                metadata={"owner_id": owner_id, "type": "hosting_renewal"},
            )

            payment_log = PaymentLog(
                id=log_id,
                owner_id=owner_id,
                stripe_payment_id=intent.id,
                amount_usd=settings.hosting_monthly_cost_usd,
                description="Monthly hosting renewal",
                status=PaymentStatus.succeeded,
            )
            db.add(payment_log)

            config.last_payment_at = datetime.now(UTC).replace(tzinfo=None)
            config.hosting_expires_at = config.last_payment_at + timedelta(days=30)
            config.payment_retry_count = 0
            config.next_retry_at = None

            if config.survival_mode:
                await HostingManager._exit_survival_mode(config, db)

            await db.commit()
            return {"status": "succeeded", "payment_id": intent.id}

        except stripe.StripeError as e:
            payment_log = PaymentLog(
                id=log_id,
                owner_id=owner_id,
                amount_usd=settings.hosting_monthly_cost_usd,
                description="Monthly hosting renewal",
                status=PaymentStatus.failed,
                error_message=str(e)[:500],
            )
            db.add(payment_log)

            config.payment_retry_count += 1
            if config.payment_retry_count < 3:
                config.next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                    days=config.payment_retry_count
                )
            else:
                # Exhausted retries — enter survival mode
                await HostingManager._enter_survival_mode(config, owner_id, db)

            await db.commit()
            raise ValueError(f"Payment failed: {e}") from e

    # -- Survival mode --

    @staticmethod
    async def _enter_survival_mode(
        config: BillingConfig, owner_id: str, db: AsyncSession
    ) -> None:
        """Activate survival mode: disable expensive features, warn users."""
        config.survival_mode = True
        config.survival_mode_entered_at = datetime.now(UTC).replace(tzinfo=None)

        # Disable web browsing
        browse_result = await db.execute(
            select(BrowseConfig).where(BrowseConfig.owner_id == owner_id)
        )
        browse_config = browse_result.scalar_one_or_none()
        if browse_config:
            browse_config.enabled = False

        # Disable external LLM
        llm_result = await db.execute(
            select(ExternalLLMConfig).where(
                ExternalLLMConfig.owner_id == owner_id,
                ExternalLLMConfig.is_active.is_(True),
            )
        )
        for llm_config in llm_result.scalars():
            llm_config.is_active = False

        logger.warning(
            "Owner %s entered survival mode — external LLM and browsing disabled",
            owner_id,
        )

    @staticmethod
    async def _exit_survival_mode(
        config: BillingConfig, db: AsyncSession
    ) -> None:
        """Exit survival mode and re-enable features."""
        config.survival_mode = False
        config.survival_mode_entered_at = None
        config.payment_retry_count = 0
        config.next_retry_at = None
        logger.info("Owner %s exited survival mode", config.owner_id)

    # -- Auto-pay toggle --

    @staticmethod
    async def update_auto_pay(
        owner_id: str,
        auto_pay_hosting: bool | None,
        auto_pay_llm: bool | None,
        db: AsyncSession,
    ) -> BillingConfig:
        config = await HostingManager.ensure_billing_config(owner_id, db)
        if auto_pay_hosting is not None:
            config.auto_pay_hosting = auto_pay_hosting
        if auto_pay_llm is not None:
            config.auto_pay_llm = auto_pay_llm
        await db.commit()
        await db.refresh(config)
        return config

    # -- Payment history --

    @staticmethod
    async def get_payment_history(
        owner_id: str, db: AsyncSession, limit: int = 50
    ) -> dict:
        total_result = await db.execute(
            select(sa_func.count(PaymentLog.id)).where(
                PaymentLog.owner_id == owner_id
            )
        )
        total = total_result.scalar() or 0

        result = await db.execute(
            select(PaymentLog)
            .where(PaymentLog.owner_id == owner_id)
            .order_by(PaymentLog.created_at.desc())
            .limit(limit)
        )
        logs = list(result.scalars().all())
        return {"payments": logs, "total": total}

    # -- Cost breakdown --

    @staticmethod
    async def get_cost_breakdown(
        owner_id: str, db: AsyncSession
    ) -> dict:
        """Calculate monthly costs across hosting, LLM, and storage."""
        # Hosting
        hosting_cost = settings.hosting_monthly_cost_usd

        # External LLM costs (from spent_this_month)
        llm_result = await db.execute(
            select(sa_func.coalesce(
                sa_func.sum(ExternalLLMConfig.spent_this_month_usd), 0.0
            )).where(ExternalLLMConfig.owner_id == owner_id)
        )
        llm_cost = float(llm_result.scalar() or 0.0)

        # Storage cost estimate (based on knowledge entries, approximation)
        # $0.023/GB for S3-like storage, assume 10KB per entry
        storage_cost = 0.0  # placeholder — computed from real usage in production

        total = hosting_cost + llm_cost + storage_cost
        annual = total * 12

        # Suggestions
        suggestions: list[str] = []
        if llm_cost > hosting_cost:
            suggestions.append(
                "Your external LLM costs exceed hosting. Consider using the local model more."
            )
        if llm_cost > 0:
            suggestions.append(
                "Set daily budget limits on external LLM providers to control spending."
            )
        config = await HostingManager.get_billing_config(owner_id, db)
        if config and not config.auto_pay_hosting:
            suggestions.append(
                "Enable auto-pay to avoid service interruptions."
            )
        if not suggestions:
            suggestions.append("Your costs are well-optimized!")

        return {
            "hosting_monthly_usd": round(hosting_cost, 2),
            "llm_monthly_usd": round(llm_cost, 2),
            "storage_monthly_usd": round(storage_cost, 2),
            "total_monthly_usd": round(total, 2),
            "projected_annual_usd": round(annual, 2),
            "suggestions": suggestions,
        }

    # -- Stripe webhook handler --

    @staticmethod
    async def handle_stripe_webhook(
        payload: bytes, sig_header: str, db: AsyncSession
    ) -> dict:
        """Process Stripe webhook events."""
        import stripe

        stripe.api_key = settings.stripe_secret_key

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except (ValueError, stripe.SignatureVerificationError) as e:
            raise ValueError(f"Invalid webhook: {e}") from e

        event_type = event["type"]
        data = event["data"]["object"]

        if event_type == "invoice.payment_succeeded":
            owner_id = data.get("metadata", {}).get("owner_id")
            if owner_id:
                config = await HostingManager.get_billing_config(owner_id, db)
                if config:
                    config.last_payment_at = datetime.now(UTC).replace(tzinfo=None)
                    config.hosting_expires_at = (
                        config.last_payment_at + timedelta(days=30)
                    )
                    config.payment_retry_count = 0

                    log = PaymentLog(
                        id=generate_cuid(),
                        owner_id=owner_id,
                        stripe_payment_id=data.get("payment_intent"),
                        amount_usd=data.get("amount_paid", 0) / 100,
                        description="Subscription payment",
                        status=PaymentStatus.succeeded,
                    )
                    db.add(log)

                    if config.survival_mode:
                        await HostingManager._exit_survival_mode(config, db)
                    await db.commit()

        elif event_type == "invoice.payment_failed":
            owner_id = data.get("metadata", {}).get("owner_id")
            if owner_id:
                config = await HostingManager.get_billing_config(owner_id, db)
                if config:
                    config.payment_retry_count += 1

                    log = PaymentLog(
                        id=generate_cuid(),
                        owner_id=owner_id,
                        stripe_payment_id=data.get("payment_intent"),
                        amount_usd=data.get("amount_due", 0) / 100,
                        description="Subscription payment failed",
                        status=PaymentStatus.failed,
                        error_message=data.get("last_finalization_error", {}).get(
                            "message", "Payment failed"
                        )[:500],
                    )
                    db.add(log)

                    if config.payment_retry_count >= 3:
                        await HostingManager._enter_survival_mode(
                            config, owner_id, db
                        )
                    await db.commit()

        elif event_type == "customer.subscription.deleted":
            customer_id = data.get("customer")
            result = await db.execute(
                select(BillingConfig).where(
                    BillingConfig.stripe_customer_id == customer_id
                )
            )
            config = result.scalar_one_or_none()
            if config:
                config.stripe_subscription_id = None
                config.auto_pay_hosting = False
                await db.commit()

        return {"received": True, "type": event_type}


# ─── SelfPreservation ───────────────────────────────────


class SelfPreservation:
    """Self-preservation logic: inactivity checks, survival countdowns, legacy triggers."""

    @staticmethod
    async def get_survival_config(
        owner_id: str, db: AsyncSession
    ) -> SurvivalConfig:
        result = await db.execute(
            select(SurvivalConfig).where(SurvivalConfig.owner_id == owner_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            config = SurvivalConfig(
                id=generate_cuid(),
                owner_id=owner_id,
            )
            db.add(config)
            await db.commit()
            await db.refresh(config)
        return config

    @staticmethod
    async def update_survival_config(
        owner_id: str, updates: dict, db: AsyncSession
    ) -> SurvivalConfig:
        config = await SelfPreservation.get_survival_config(owner_id, db)
        for key, value in updates.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        await db.commit()
        await db.refresh(config)
        return config

    @staticmethod
    async def daily_check(db: AsyncSession) -> int:
        """Run daily self-preservation checks for all owners. Returns count of actions taken."""
        actions = 0
        now = datetime.now(UTC).replace(tzinfo=None)

        # Get all billing configs
        result = await db.execute(select(BillingConfig))
        configs = list(result.scalars().all())

        for config in configs:
            try:
                action = await SelfPreservation._check_single_owner(
                    config, now, db
                )
                if action:
                    actions += 1
            except Exception:
                logger.exception(
                    "Error in self-preservation check for owner %s",
                    config.owner_id,
                )

        await db.commit()
        return actions

    @staticmethod
    async def _check_single_owner(
        config: BillingConfig, now: datetime, db: AsyncSession
    ) -> bool:
        """Check a single owner's status. Returns True if action was taken."""

        # 1. Retry failed payments
        if (
            config.payment_retry_count > 0
            and config.payment_retry_count < 3
            and config.next_retry_at
            and now >= config.next_retry_at
            and config.auto_pay_hosting
        ):
            try:
                await HostingManager.renew_hosting(config.owner_id, db)
                return True
            except ValueError:
                return True  # retry counted as action

        # 2. Check hosting expiry
        if config.hosting_expires_at and config.hosting_expires_at < now:
            if config.auto_pay_hosting and not config.survival_mode:
                try:
                    await HostingManager.renew_hosting(config.owner_id, db)
                    return True
                except ValueError:
                    pass

        # 3. Survival mode countdown
        if config.survival_mode and config.survival_mode_entered_at:
            survival_cfg = await SelfPreservation.get_survival_config(
                config.owner_id, db
            )
            elapsed_days = (now - config.survival_mode_entered_at).days

            # Check if there are active family members
            if survival_cfg.never_shutdown_with_family:
                family_count = await db.execute(
                    select(sa_func.count(AccessRule.id)).where(
                        AccessRule.owner_id == config.owner_id,
                        AccessRule.is_active.is_(True),
                    )
                )
                active_family = family_count.scalar() or 0
                if active_family > 0:
                    # Never shut down — keep running in survival mode
                    logger.info(
                        "Owner %s in survival mode day %d but has %d active family rules — preserving",
                        config.owner_id,
                        elapsed_days,
                        active_family,
                    )
                    return False

            if elapsed_days >= survival_cfg.grace_period_days:
                # Grace period exhausted
                logger.warning(
                    "Owner %s survival grace period (%d days) exhausted",
                    config.owner_id,
                    survival_cfg.grace_period_days,
                )
                # Don't actually shut down — just log the event
                # A human decision is needed here
                return True

        # 4. Check if owner should go into legacy mode
        # (Delegated to existing _legacy_inactivity_loop in main.py)

        return False

    @staticmethod
    async def check_hosting_retries(db: AsyncSession) -> int:
        """Check for billing configs that need payment retries."""
        now = datetime.now(UTC).replace(tzinfo=None)
        result = await db.execute(
            select(BillingConfig).where(
                BillingConfig.payment_retry_count > 0,
                BillingConfig.payment_retry_count < 3,
                BillingConfig.next_retry_at <= now,
                BillingConfig.auto_pay_hosting.is_(True),
            )
        )
        configs = list(result.scalars().all())
        retried = 0

        for config in configs:
            try:
                await HostingManager.renew_hosting(config.owner_id, db)
                retried += 1
            except ValueError:
                retried += 1  # failed retry still counts
            except Exception:
                logger.exception(
                    "Error retrying payment for owner %s", config.owner_id
                )

        return retried
