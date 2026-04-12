"""Web Push notification service.

Wraps :mod:`pywebpush` and persists subscriptions in PostgreSQL via
:class:`app.models.owner.PushSubscription`.

The module is import-safe even when ``pywebpush`` is not installed — failures
are surfaced lazily so unit tests that don't exercise push do not require the
optional dependency.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.owner import PushSubscription as PushSubscriptionModel
from app.models.push import PushSubscriptionCreate

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PushNotConfiguredError(RuntimeError):
    """Raised when push is invoked but VAPID keys are not configured."""


class PushNotificationService:
    """Manage push subscriptions and dispatch notifications.

    Subscriptions are stored per owner. ``send_to_owner`` fans out to every
    subscription belonging to the owner. Endpoints that return 404/410 are
    automatically removed (per RFC 8030 best practice).
    """

    def __init__(self) -> None:
        self._vapid_claims = {"sub": settings.vapid_subject}

    @property
    def configured(self) -> bool:
        return bool(
            settings.push_enabled
            and settings.vapid_public_key
            and settings.vapid_private_key
        )

    async def subscribe(
        self,
        owner_id: str,
        payload: PushSubscriptionCreate,
        db: AsyncSession,
    ) -> PushSubscriptionModel:
        """Idempotently upsert a subscription keyed by ``endpoint``."""
        existing = await db.scalar(
            select(PushSubscriptionModel).where(
                PushSubscriptionModel.endpoint == payload.endpoint
            )
        )
        if existing is not None:
            existing.owner_id = owner_id
            existing.p256dh = payload.keys.p256dh
            existing.auth = payload.keys.auth
            existing.user_agent = payload.user_agent
            existing.last_used_at = _utcnow()
            await db.commit()
            await db.refresh(existing)
            return existing

        sub = PushSubscriptionModel(
            id=secrets.token_urlsafe(16),
            owner_id=owner_id,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            user_agent=payload.user_agent,
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
        return sub

    async def unsubscribe(self, owner_id: str, endpoint: str, db: AsyncSession) -> bool:
        sub = await db.scalar(
            select(PushSubscriptionModel).where(
                PushSubscriptionModel.endpoint == endpoint,
                PushSubscriptionModel.owner_id == owner_id,
            )
        )
        if sub is None:
            return False
        await db.delete(sub)
        await db.commit()
        return True

    async def list_for_owner(
        self, owner_id: str, db: AsyncSession
    ) -> list[PushSubscriptionModel]:
        result = await db.scalars(
            select(PushSubscriptionModel).where(
                PushSubscriptionModel.owner_id == owner_id
            )
        )
        return list(result.all())

    async def send_to_owner(
        self,
        owner_id: str,
        title: str,
        body: str,
        db: AsyncSession,
        data: dict[str, Any] | None = None,
        tag: str | None = None,
    ) -> int:
        """Send a notification to every subscription belonging to ``owner_id``.

        Returns the number of successful deliveries. Subscriptions that the
        push service rejects with 404/410 are pruned automatically.
        """
        if not self.configured:
            logger.debug("Push not configured; skipping notification for %s", owner_id)
            return 0

        subs = await self.list_for_owner(owner_id, db)
        if not subs:
            return 0

        try:
            from pywebpush import WebPushException, webpush  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("pywebpush is not installed; cannot send notifications")
            return 0

        payload = json.dumps(
            {
                "title": title,
                "body": body,
                "data": data or {},
                "tag": tag,
            }
        )

        sent = 0
        stale: list[PushSubscriptionModel] = []
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims=dict(self._vapid_claims),
                    ttl=settings.push_ttl_seconds,
                )
                sub.last_used_at = _utcnow()
                sent += 1
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None) if exc.response else None
                if status in (404, 410):
                    stale.append(sub)
                else:
                    logger.warning("Push delivery failed for %s: %s", sub.endpoint, exc)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Unexpected push error: %s", exc)

        for sub in stale:
            await db.delete(sub)
        if stale or sent:
            await db.commit()

        return sent


_service: PushNotificationService | None = None


def get_push_service() -> PushNotificationService:
    """Return the singleton push service."""
    global _service
    if _service is None:
        _service = PushNotificationService()
    return _service
