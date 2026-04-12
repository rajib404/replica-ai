import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.models.personality import (
    CommunicationStyle,
    EmotionDetection,
    EmotionTrendEntry,
    EmotionTrendResponse,
    HumorPatterns,
    PersonalityProfileResponse,
    TraitItem,
    TraitListResponse,
    UpdateTraitsRequest,
    RefreshPersonalityRequest,
)
from app.services.personality import EmotionalSupport, PersonalityTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/personality", tags=["personality"])


@router.get("/profile", response_model=PersonalityProfileResponse)
async def get_personality_profile(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> PersonalityProfileResponse:
    """Get the owner's personality profile."""
    profile = await PersonalityTracker.get_or_create_profile(auth.subject_id, db)
    await db.commit()

    traits_data = profile.traits or {}
    trait_items = traits_data.get("items", []) if isinstance(traits_data, dict) else []
    confirmed = profile.owner_confirmed or {}

    values_data = profile.values_and_beliefs or {}
    value_items = values_data.get("items", []) if isinstance(values_data, dict) else []

    return PersonalityProfileResponse(
        owner_id=profile.owner_id,
        traits=[
            TraitItem(
                name=t.get("name", ""),
                value=t.get("value", ""),
                confidence=t.get("confidence", 0.5),
                confirmed=confirmed.get(t.get("name", "")),
            )
            for t in trait_items
        ],
        communication_style=CommunicationStyle(**(profile.communication_style or {})),
        humor_patterns=HumorPatterns(**(profile.humor_patterns or {})),
        values_and_beliefs=[
            TraitItem(
                name=v.get("name", ""),
                value=v.get("value", ""),
                confidence=v.get("confidence", 0.5),
                confirmed=confirmed.get(f"value:{v.get('name', '')}"),
            )
            for v in value_items
        ],
        phrases_and_idioms=profile.phrases_and_idioms or [],
        emotional_baseline=profile.emotional_baseline or {},
        messages_analyzed=profile.messages_analyzed,
        last_analysis_at=(
            profile.last_analysis_at.isoformat() if profile.last_analysis_at else None
        ),
    )


@router.post("/refresh", response_model=PersonalityProfileResponse)
async def refresh_personality(
    body: RefreshPersonalityRequest = RefreshPersonalityRequest(),
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
) -> PersonalityProfileResponse:
    """Trigger a personality analysis refresh."""
    profile = await PersonalityTracker.analyze_message_batch(
        owner_id=auth.subject_id, db=db, ai=ai, force=body.force
    )
    await db.commit()

    traits_data = profile.traits or {}
    trait_items = traits_data.get("items", []) if isinstance(traits_data, dict) else []
    confirmed = profile.owner_confirmed or {}

    values_data = profile.values_and_beliefs or {}
    value_items = values_data.get("items", []) if isinstance(values_data, dict) else []

    return PersonalityProfileResponse(
        owner_id=profile.owner_id,
        traits=[
            TraitItem(
                name=t.get("name", ""),
                value=t.get("value", ""),
                confidence=t.get("confidence", 0.5),
                confirmed=confirmed.get(t.get("name", "")),
            )
            for t in trait_items
        ],
        communication_style=CommunicationStyle(**(profile.communication_style or {})),
        humor_patterns=HumorPatterns(**(profile.humor_patterns or {})),
        values_and_beliefs=[
            TraitItem(
                name=v.get("name", ""),
                value=v.get("value", ""),
                confidence=v.get("confidence", 0.5),
                confirmed=confirmed.get(f"value:{v.get('name', '')}"),
            )
            for v in value_items
        ],
        phrases_and_idioms=profile.phrases_and_idioms or [],
        emotional_baseline=profile.emotional_baseline or {},
        messages_analyzed=profile.messages_analyzed,
        last_analysis_at=(
            profile.last_analysis_at.isoformat() if profile.last_analysis_at else None
        ),
    )


@router.get("/traits", response_model=TraitListResponse)
async def get_personality_traits(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> TraitListResponse:
    """Get just the personality traits (for quick review)."""
    profile = await PersonalityTracker.get_profile(auth.subject_id, db)
    if not profile:
        return TraitListResponse(traits=[], total=0)

    traits_data = profile.traits or {}
    trait_items = traits_data.get("items", []) if isinstance(traits_data, dict) else []
    confirmed = profile.owner_confirmed or {}

    values_data = profile.values_and_beliefs or {}
    value_items = values_data.get("items", []) if isinstance(values_data, dict) else []

    all_traits = [
        TraitItem(
            name=t.get("name", ""),
            value=t.get("value", ""),
            confidence=t.get("confidence", 0.5),
            confirmed=confirmed.get(t.get("name", "")),
        )
        for t in trait_items
    ] + [
        TraitItem(
            name=f"value:{v.get('name', '')}",
            value=v.get("value", ""),
            confidence=v.get("confidence", 0.5),
            confirmed=confirmed.get(f"value:{v.get('name', '')}"),
        )
        for v in value_items
    ]

    return TraitListResponse(traits=all_traits, total=len(all_traits))


@router.put("/traits", response_model=TraitListResponse)
async def update_traits(
    body: UpdateTraitsRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> TraitListResponse:
    """Confirm or reject personality traits."""
    profile = await PersonalityTracker.get_or_create_profile(auth.subject_id, db)
    confirmed = dict(profile.owner_confirmed or {})

    for update in body.updates:
        confirmed[update.trait_name] = update.confirmed

    profile.owner_confirmed = confirmed
    await db.flush()
    await db.commit()

    # Return updated traits
    traits_data = profile.traits or {}
    trait_items = traits_data.get("items", []) if isinstance(traits_data, dict) else []

    values_data = profile.values_and_beliefs or {}
    value_items = values_data.get("items", []) if isinstance(values_data, dict) else []

    all_traits = [
        TraitItem(
            name=t.get("name", ""),
            value=t.get("value", ""),
            confidence=t.get("confidence", 0.5),
            confirmed=confirmed.get(t.get("name", "")),
        )
        for t in trait_items
    ] + [
        TraitItem(
            name=f"value:{v.get('name', '')}",
            value=v.get("value", ""),
            confidence=v.get("confidence", 0.5),
            confirmed=confirmed.get(f"value:{v.get('name', '')}"),
        )
        for v in value_items
    ]

    return TraitListResponse(traits=all_traits, total=len(all_traits))


@router.get("/emotions", response_model=EmotionTrendResponse)
async def get_emotion_trend(
    days: int = 7,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> EmotionTrendResponse:
    """Get the owner's emotional trend over the past N days."""
    trend = await EmotionalSupport.get_emotion_trend(auth.subject_id, db, days=days)
    latest = await EmotionalSupport.get_latest_emotion(auth.subject_id, db)

    current: EmotionDetection | None = None
    if latest:
        current = EmotionDetection(
            emotion=latest.emotion,
            intensity=latest.intensity,
            secondary_emotions=latest.secondary_emotions or [],
            context_summary=latest.context_summary,
        )

    return EmotionTrendResponse(
        current_emotion=current,
        trend=[
            EmotionTrendEntry(
                date=t["date"],
                emotion=t["emotion"],
                intensity=t["intensity"],
                count=t["count"],
            )
            for t in trend
        ],
        period_days=days,
    )
