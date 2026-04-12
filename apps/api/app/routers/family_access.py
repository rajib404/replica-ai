from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.models.family_access import (
    AccessRuleListResponse,
    AccessRuleResponse,
    AccessTemplateResponse,
    CreateAccessRuleRequest,
    FamilySessionResponse,
    FamilyVerifyRequest,
    GenerateInviteRequest,
    InviteResponse,
    LegacyActivateResponse,
    LegacyConfigResponse,
    LegacyConfigureRequest,
    TemplateListResponse,
    UpdateAccessRuleRequest,
)
from app.services.family_access import FamilyAccessManager

router = APIRouter(prefix="/api/access", tags=["family-access"])

manager = FamilyAccessManager()


# ─── Access Rules CRUD ──────────────────────────────────


@router.post("/rules", status_code=201, response_model=AccessRuleResponse)
async def create_rule(
    body: CreateAccessRuleRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> AccessRuleResponse:
    """Create a new family access rule."""
    if not body.grantee_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="grantee_name is required and must be non-empty.",
        )
    return await manager.create_access_rule(auth.subject_id, body, db)


@router.get("/rules", response_model=AccessRuleListResponse)
async def list_rules(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> AccessRuleListResponse:
    """List all access rules for this owner."""
    rules = await manager.list_access_rules(auth.subject_id, db)
    return AccessRuleListResponse(rules=rules, total=len(rules))


@router.get("/rules/{rule_id}", response_model=AccessRuleResponse)
async def get_rule(
    rule_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> AccessRuleResponse:
    """Get a single access rule."""
    try:
        return await manager.get_access_rule(rule_id, auth.subject_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.put("/rules/{rule_id}", response_model=AccessRuleResponse)
async def update_rule(
    rule_id: str,
    body: UpdateAccessRuleRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> AccessRuleResponse:
    """Update an access rule."""
    updates = body.model_dump(exclude_unset=True)
    try:
        return await manager.update_access_rule(rule_id, auth.subject_id, updates, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an access rule."""
    try:
        await manager.delete_access_rule(rule_id, auth.subject_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# ─── Invites ────────────────────────────────────────────


@router.post("/invite/{rule_id}", status_code=201, response_model=InviteResponse)
async def generate_invite(
    rule_id: str,
    body: GenerateInviteRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """Generate a family invite link + QR code for an access rule."""
    try:
        return await manager.generate_family_invite(
            rule_id=rule_id,
            owner_id=auth.subject_id,
            is_reusable=body.is_reusable,
            max_uses=body.max_uses,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# ─── Verification (public — no owner auth) ──────────────


@router.post("/verify", response_model=FamilySessionResponse)
async def verify_family(
    body: FamilyVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> FamilySessionResponse:
    """Verify a family invite token and return a scoped session."""
    return await manager.validate_family_access(
        invite_token=body.invite_token,
        verification_value=body.verification_value,
        db=db,
    )


# ─── Templates ──────────────────────────────────────────


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    auth: AuthContext = Depends(require_role("owner")),
) -> TemplateListResponse:
    """List available access rule templates."""
    templates = FamilyAccessManager.get_templates()
    return TemplateListResponse(templates=templates)


# ─── Legacy Mode ────────────────────────────────────────


@router.get("/legacy", response_model=LegacyConfigResponse | None)
async def get_legacy_config(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> LegacyConfigResponse | None:
    """Get the current legacy mode configuration."""
    return await manager.get_legacy_config(auth.subject_id, db)


@router.put("/legacy/configure", response_model=LegacyConfigResponse)
async def configure_legacy(
    body: LegacyConfigureRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> LegacyConfigResponse:
    """Create or update legacy mode configuration."""
    try:
        return await manager.configure_legacy(
            owner_id=auth.subject_id,
            trigger_type=body.trigger_type,
            inactivity_days=body.inactivity_days,
            trusted_person_rule_id=body.trusted_person_rule_id,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@router.post("/legacy/activate", response_model=LegacyActivateResponse)
async def activate_legacy(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> LegacyActivateResponse:
    """Manually activate legacy mode."""
    activated, message, activated_at = await manager.activate_legacy(
        auth.subject_id, db
    )
    return LegacyActivateResponse(
        activated=activated,
        message=message,
        activated_at=activated_at,
    )
