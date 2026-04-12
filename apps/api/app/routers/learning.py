"""Learning router: knowledge gaps, topic learning, reports, preferences."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.models.learning import (
    ConsolidationResult,
    KnowledgeGapsResponse,
    LearningPreferences,
    LearningPreferencesResponse,
    LearningReportEntry,
    LearningReportResponse,
    LearnTopicRequest,
    LearnTopicResponse,
    StaleKnowledgeResponse,
)
from app.services.self_learner import SelfLearner

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/gaps", response_model=KnowledgeGapsResponse)
async def get_knowledge_gaps(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeGapsResponse:
    """Identify knowledge gaps in the replica's knowledge base."""
    return await SelfLearner.identify_knowledge_gaps(auth.subject_id, db)


@router.post("/learn", response_model=LearnTopicResponse)
async def learn_topic(
    body: LearnTopicRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> LearnTopicResponse:
    """Research and learn about a specific topic."""
    return await SelfLearner.learn_topic(auth.subject_id, body.topic, body.depth, db)


@router.get("/report", response_model=LearningReportResponse)
async def get_learning_report(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> LearningReportResponse:
    """Get paginated learning history."""
    logs, total = await SelfLearner.get_learning_report(
        auth.subject_id, db, page=page, page_size=page_size
    )

    entries = [
        LearningReportEntry(
            id=log.id,
            topic=log.topic,
            depth=log.depth,
            sources_used=log.sources_used or [],
            entries_created=log.entries_created,
            summary=log.summary,
            status=log.status,
            error_message=log.error_message,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]

    return LearningReportResponse(
        entries=entries, total=total, page=page, page_size=page_size
    )


@router.get("/preferences", response_model=LearningPreferencesResponse)
async def get_preferences(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> LearningPreferencesResponse:
    """Get current learning preferences."""
    config = await SelfLearner.get_preferences(auth.subject_id, db)

    prefs = LearningPreferences(
        enabled=config.enabled if config else False,
        auto_topics=config.auto_topics if config else [],
        ignore_topics=config.ignore_topics if config else [],
        depth=config.depth if config else "moderate",
        schedule_hour_utc=config.schedule_hour_utc if config else 3,
        max_daily_web_searches=config.max_daily_web_searches if config else 10,
        use_external_llm=config.use_external_llm if config else False,
    )

    return LearningPreferencesResponse(
        preferences=prefs, owner_id=auth.subject_id
    )


@router.put("/preferences", response_model=LearningPreferencesResponse)
async def update_preferences(
    body: LearningPreferences,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> LearningPreferencesResponse:
    """Create or update learning preferences."""
    config = await SelfLearner.upsert_preferences(
        auth.subject_id,
        db,
        enabled=body.enabled,
        auto_topics=body.auto_topics,
        ignore_topics=body.ignore_topics,
        depth=body.depth,
        schedule_hour_utc=body.schedule_hour_utc,
        max_daily_web_searches=body.max_daily_web_searches,
        use_external_llm=body.use_external_llm,
    )

    prefs = LearningPreferences(
        enabled=config.enabled,
        auto_topics=config.auto_topics,
        ignore_topics=config.ignore_topics,
        depth=config.depth,
        schedule_hour_utc=config.schedule_hour_utc,
        max_daily_web_searches=config.max_daily_web_searches,
        use_external_llm=config.use_external_llm,
    )

    return LearningPreferencesResponse(
        preferences=prefs, owner_id=auth.subject_id
    )


@router.get("/stale", response_model=StaleKnowledgeResponse)
async def get_stale_knowledge(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> StaleKnowledgeResponse:
    """Find knowledge entries that may be outdated."""
    return await SelfLearner.review_stale_knowledge(auth.subject_id, db)


@router.post("/consolidate", response_model=ConsolidationResult)
async def consolidate_knowledge(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ConsolidationResult:
    """Consolidate similar knowledge entries into comprehensive summaries."""
    return await SelfLearner.consolidate_knowledge(auth.subject_id, db)
