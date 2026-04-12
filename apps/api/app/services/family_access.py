"""Family access management: rules, invites, verification, and legacy mode."""

import base64
import io
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

import qrcode
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_secret, verify_secret
from app.models.family_access import (
    AccessRuleResponse,
    AccessTemplateResponse,
    CreateAccessRuleRequest,
    FamilySessionResponse,
    InviteResponse,
    LegacyConfigResponse,
)
from app.models.owner import (
    AccessLevel,
    AccessRule,
    FamilyInvite,
    LegacyConfig,
    LegacyTriggerType,
    VerificationMethod,
)

logger = logging.getLogger(__name__)


def _generate_cuid() -> str:
    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _generate_qr_base64(url: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _rule_to_response(rule: AccessRule) -> AccessRuleResponse:
    return AccessRuleResponse(
        id=rule.id,
        owner_id=rule.owner_id,
        grantee_name=rule.grantee_name,
        grantee_relation=rule.grantee_relation,
        access_level=rule.access_level.value,
        verification_method=rule.verification_method.value,
        is_active=rule.is_active,
        valid_from=rule.valid_from,
        valid_until=rule.valid_until,
        topic_restrictions=rule.topic_restrictions,
        time_restrictions=rule.time_restrictions,
        template_name=rule.template_name,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _legacy_to_response(config: LegacyConfig) -> LegacyConfigResponse:
    return LegacyConfigResponse(
        id=config.id,
        owner_id=config.owner_id,
        trigger_type=config.trigger_type.value,
        inactivity_days=config.inactivity_days,
        trusted_person_rule_id=config.trusted_person_rule_id,
        is_active=config.is_active,
        activated_at=config.activated_at,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


# ─── Predefined templates ───────────────────────────────

TEMPLATES: list[AccessTemplateResponse] = [
    AccessTemplateResponse(
        name="spouse_full",
        label="Spouse — Full Access",
        description="Full access with voice verification, no topic restrictions.",
        config=CreateAccessRuleRequest(
            grantee_name="",
            grantee_relation="spouse",
            access_level="full",
            verification_method="voice_match",
            template_name="spouse_full",
        ),
    ),
    AccessTemplateResponse(
        name="child_stories",
        label="Child — Stories & Memories",
        description="Limited to family stories, photos, voice messages. No financial or medical topics.",
        config=CreateAccessRuleRequest(
            grantee_name="",
            grantee_relation="son",
            access_level="limited",
            verification_method="secret_word",
            topic_restrictions={
                "allowed": ["family stories", "photos", "voice messages", "memories", "recipes", "traditions"],
                "blocked": ["financial", "medical", "legal", "passwords", "accounts"],
            },
            template_name="child_stories",
        ),
    ),
    AccessTemplateResponse(
        name="grandchild_legacy",
        label="Grandchild — Legacy Mode",
        description="Read-only access to curated knowledge. Model introduces itself as grandfather/grandmother.",
        config=CreateAccessRuleRequest(
            grantee_name="",
            grantee_relation="grandson",
            access_level="read_only",
            verification_method="secret_word",
            topic_restrictions={
                "allowed": ["family history", "life lessons", "stories", "memories", "advice", "wisdom"],
                "blocked": ["financial", "medical", "legal", "passwords"],
            },
            template_name="grandchild_legacy",
        ),
    ),
    AccessTemplateResponse(
        name="trusted_friend",
        label="Trusted Friend",
        description="Limited chat on specific topics only. Expires in 1 year.",
        config=CreateAccessRuleRequest(
            grantee_name="",
            grantee_relation="friend",
            access_level="limited",
            verification_method="secret_word",
            topic_restrictions={
                "allowed": ["general conversation", "shared interests"],
                "blocked": ["financial", "medical", "legal", "family private", "passwords"],
            },
            template_name="trusted_friend",
        ),
    ),
]


class FamilyAccessManager:
    """Manages family access rules, invitations, verification, and legacy mode."""

    # ── Access Rules CRUD ────────────────────────────────

    async def create_access_rule(
        self,
        owner_id: str,
        request: CreateAccessRuleRequest,
        db: AsyncSession,
    ) -> AccessRuleResponse:
        verification_hash = None
        if request.verification_value:
            verification_hash = hash_secret(request.verification_value)

        # Compute valid_until for template-based rules
        valid_until = request.valid_until
        if request.template_name == "trusted_friend" and not valid_until:
            valid_until = _utcnow() + timedelta(days=365)

        rule = AccessRule(
            id=_generate_cuid(),
            owner_id=owner_id,
            grantee_name=request.grantee_name,
            grantee_relation=request.grantee_relation,
            access_level=AccessLevel(request.access_level),
            verification_method=VerificationMethod(request.verification_method),
            verification_value_hash=verification_hash,
            is_active=True,
            valid_from=_utcnow(),
            valid_until=valid_until,
            topic_restrictions=request.topic_restrictions.model_dump() if request.topic_restrictions else None,
            time_restrictions=request.time_restrictions.model_dump() if request.time_restrictions else None,
            template_name=request.template_name,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return _rule_to_response(rule)

    async def get_access_rule(
        self, rule_id: str, owner_id: str, db: AsyncSession
    ) -> AccessRuleResponse:
        result = await db.execute(
            select(AccessRule).where(
                AccessRule.id == rule_id,
                AccessRule.owner_id == owner_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Access rule not found")
        return _rule_to_response(rule)

    async def list_access_rules(
        self, owner_id: str, db: AsyncSession
    ) -> list[AccessRuleResponse]:
        result = await db.execute(
            select(AccessRule)
            .where(AccessRule.owner_id == owner_id)
            .order_by(AccessRule.created_at.desc())
        )
        rules = list(result.scalars().all())
        return [_rule_to_response(r) for r in rules]

    async def update_access_rule(
        self,
        rule_id: str,
        owner_id: str,
        updates: dict,
        db: AsyncSession,
    ) -> AccessRuleResponse:
        result = await db.execute(
            select(AccessRule).where(
                AccessRule.id == rule_id,
                AccessRule.owner_id == owner_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Access rule not found")

        if "grantee_name" in updates and updates["grantee_name"] is not None:
            rule.grantee_name = updates["grantee_name"]
        if "grantee_relation" in updates:
            rule.grantee_relation = updates["grantee_relation"]
        if "access_level" in updates and updates["access_level"] is not None:
            rule.access_level = AccessLevel(updates["access_level"])
        if "verification_method" in updates and updates["verification_method"] is not None:
            rule.verification_method = VerificationMethod(updates["verification_method"])
        if "verification_value" in updates and updates["verification_value"] is not None:
            rule.verification_value_hash = hash_secret(updates["verification_value"])
        if "is_active" in updates and updates["is_active"] is not None:
            rule.is_active = updates["is_active"]
        if "valid_until" in updates:
            rule.valid_until = updates["valid_until"]
        if "topic_restrictions" in updates:
            tr = updates["topic_restrictions"]
            rule.topic_restrictions = tr.model_dump() if tr else None
        if "time_restrictions" in updates:
            tr = updates["time_restrictions"]
            rule.time_restrictions = tr.model_dump() if tr else None

        await db.commit()
        await db.refresh(rule)
        return _rule_to_response(rule)

    async def delete_access_rule(
        self, rule_id: str, owner_id: str, db: AsyncSession
    ) -> None:
        result = await db.execute(
            select(AccessRule).where(
                AccessRule.id == rule_id,
                AccessRule.owner_id == owner_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Access rule not found")
        await db.delete(rule)
        await db.commit()

    # ── Invites ──────────────────────────────────────────

    async def generate_family_invite(
        self,
        rule_id: str,
        owner_id: str,
        is_reusable: bool,
        max_uses: int,
        db: AsyncSession,
    ) -> InviteResponse:
        # Verify rule exists and belongs to owner
        result = await db.execute(
            select(AccessRule).where(
                AccessRule.id == rule_id,
                AccessRule.owner_id == owner_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Access rule not found")

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_secret(raw_token)
        expires_at = _utcnow() + timedelta(hours=settings.family_invite_expire_hours)

        invite = FamilyInvite(
            id=_generate_cuid(),
            rule_id=rule_id,
            token_hash=token_hash,
            is_reusable=is_reusable,
            uses_remaining=max_uses if is_reusable else 1,
            expires_at=expires_at,
        )
        db.add(invite)
        await db.commit()
        await db.refresh(invite)

        invite_url = f"{settings.host_url}/family/join?token={raw_token}"
        qr_base64 = _generate_qr_base64(invite_url)

        return InviteResponse(
            invite_id=invite.id,
            invite_url=invite_url,
            invite_token=raw_token,
            qr_code_base64=qr_base64,
            is_reusable=invite.is_reusable,
            uses_remaining=invite.uses_remaining,
            expires_at=invite.expires_at,
        )

    # ── Family Verification ──────────────────────────────

    async def validate_family_access(
        self,
        invite_token: str,
        verification_value: str | None,
        db: AsyncSession,
    ) -> FamilySessionResponse:
        # Find the invite by trying all non-expired invites
        now = _utcnow()
        result = await db.execute(
            select(FamilyInvite).where(
                FamilyInvite.expires_at > now,
                FamilyInvite.uses_remaining > 0,
            )
        )
        invites = list(result.scalars().all())

        matched_invite: FamilyInvite | None = None
        for inv in invites:
            if verify_secret(invite_token, inv.token_hash):
                matched_invite = inv
                break

        if not matched_invite:
            return FamilySessionResponse(
                verified=False,
                message="Invalid or expired invite link.",
            )

        # Load the access rule
        rule_result = await db.execute(
            select(AccessRule).where(AccessRule.id == matched_invite.rule_id)
        )
        rule = rule_result.scalar_one_or_none()
        if not rule or not rule.is_active:
            return FamilySessionResponse(
                verified=False,
                message="This access rule is no longer active.",
            )

        # Check time validity
        if rule.valid_until and now > rule.valid_until:
            return FamilySessionResponse(
                verified=False,
                message="This access has expired.",
            )

        # Check time-of-day restrictions
        if rule.time_restrictions:
            tr = rule.time_restrictions
            current_hour = now.hour
            days_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
            allowed_days = [days_map.get(d, -1) for d in tr.get("days", [])]
            if now.weekday() not in allowed_days:
                return FamilySessionResponse(
                    verified=False,
                    message="Access is not available at this time.",
                )
            start_h = tr.get("start_hour", 0)
            end_h = tr.get("end_hour", 23)
            if not (start_h <= current_hour <= end_h):
                return FamilySessionResponse(
                    verified=False,
                    message="Access is not available at this hour.",
                )

        # Verify identity if rule requires it
        if rule.verification_method != VerificationMethod.none:
            if rule.verification_method in (
                VerificationMethod.secret_word,
                VerificationMethod.secret_event,
            ):
                if not verification_value:
                    return FamilySessionResponse(
                        verified=False,
                        message=f"Verification required: {rule.verification_method.value}",
                    )
                if not rule.verification_value_hash:
                    return FamilySessionResponse(
                        verified=False,
                        message="Verification not configured for this rule.",
                    )
                if not verify_secret(verification_value, rule.verification_value_hash):
                    return FamilySessionResponse(
                        verified=False,
                        message="Verification failed. Incorrect answer.",
                    )
            elif rule.verification_method == VerificationMethod.voice_match:
                return FamilySessionResponse(
                    verified=False,
                    message="Voice verification required. Use /api/verify/voice/check.",
                )

        # Decrement invite uses
        if not matched_invite.is_reusable:
            matched_invite.uses_remaining -= 1
        elif matched_invite.uses_remaining > 0:
            matched_invite.uses_remaining -= 1

        await db.commit()

        # Create a scoped family member session token
        session_token = create_access_token(
            subject=rule.owner_id,
            role="family_member",
            extra={
                "rule_id": rule.id,
                "access_level": rule.access_level.value,
                "grantee_name": rule.grantee_name,
            },
        )

        return FamilySessionResponse(
            verified=True,
            message=f"Welcome, {rule.grantee_name}!",
            session_token=session_token,
            access_level=rule.access_level.value,
            grantee_name=rule.grantee_name,
            topic_restrictions=rule.topic_restrictions,
            time_restrictions=rule.time_restrictions,
        )

    # ── Templates ────────────────────────────────────────

    @staticmethod
    def get_templates() -> list[AccessTemplateResponse]:
        return TEMPLATES

    # ── Legacy Mode ──────────────────────────────────────

    async def get_legacy_config(
        self, owner_id: str, db: AsyncSession
    ) -> LegacyConfigResponse | None:
        result = await db.execute(
            select(LegacyConfig).where(LegacyConfig.owner_id == owner_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return None
        return _legacy_to_response(config)

    async def configure_legacy(
        self,
        owner_id: str,
        trigger_type: str,
        inactivity_days: int,
        trusted_person_rule_id: str | None,
        db: AsyncSession,
    ) -> LegacyConfigResponse:
        # Validate trusted_person_rule_id if provided
        if trigger_type == "trusted_person" and trusted_person_rule_id:
            rule_result = await db.execute(
                select(AccessRule).where(
                    AccessRule.id == trusted_person_rule_id,
                    AccessRule.owner_id == owner_id,
                )
            )
            if not rule_result.scalar_one_or_none():
                raise ValueError("Trusted person rule not found")

        # Upsert
        result = await db.execute(
            select(LegacyConfig).where(LegacyConfig.owner_id == owner_id)
        )
        config = result.scalar_one_or_none()

        if config:
            config.trigger_type = LegacyTriggerType(trigger_type)
            config.inactivity_days = inactivity_days
            config.trusted_person_rule_id = trusted_person_rule_id
        else:
            config = LegacyConfig(
                id=_generate_cuid(),
                owner_id=owner_id,
                trigger_type=LegacyTriggerType(trigger_type),
                inactivity_days=inactivity_days,
                trusted_person_rule_id=trusted_person_rule_id,
            )
            db.add(config)

        await db.commit()
        await db.refresh(config)
        return _legacy_to_response(config)

    async def activate_legacy(
        self, owner_id: str, db: AsyncSession
    ) -> tuple[bool, str, datetime | None]:
        result = await db.execute(
            select(LegacyConfig).where(LegacyConfig.owner_id == owner_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return False, "Legacy mode not configured. Configure it first.", None

        if config.is_active:
            return False, "Legacy mode is already active.", config.activated_at

        config.is_active = True
        config.activated_at = _utcnow()
        await db.commit()
        await db.refresh(config)

        logger.info("Legacy mode activated for owner %s", owner_id)
        return True, "Legacy mode has been activated.", config.activated_at

    @staticmethod
    async def check_inactivity_triggers(db: AsyncSession) -> int:
        """Background job: check if any owner's inactivity threshold has been reached."""
        result = await db.execute(
            select(LegacyConfig).where(
                LegacyConfig.is_active == False,  # noqa: E712
                LegacyConfig.trigger_type == LegacyTriggerType.inactivity,
            )
        )
        configs = list(result.scalars().all())

        activated = 0
        now = _utcnow()

        for config in configs:
            # Check owner's last activity (updated_at on Owner table)
            from app.models.owner import Owner

            owner_result = await db.execute(
                select(Owner).where(Owner.id == config.owner_id)
            )
            owner = owner_result.scalar_one_or_none()
            if not owner:
                continue

            cutoff = now - timedelta(days=config.inactivity_days)
            if owner.updated_at < cutoff:
                config.is_active = True
                config.activated_at = now
                activated += 1
                logger.info(
                    "Legacy mode auto-activated for owner %s (inactive %d days)",
                    config.owner_id,
                    config.inactivity_days,
                )

        if activated:
            await db.commit()

        return activated
