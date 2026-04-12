import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api_docs import API_DESCRIPTION, CONTACT_INFO, LICENSE_INFO, TAGS_METADATA
from app.core.background_loops import BackgroundLoopController, set_controller
from app.core.config import settings
from app.core.database import async_session
from app.core.exception_handlers import register_exception_handlers
from app.core.request_limits import RequestSizeLimitMiddleware
from app.core.security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.routers import auth, billing, chat, external_llm, face, family_access, family_chat, finetune, health, instances, knowledge, language, learning, model, personality, push, search, security, sync, video_call, voice, voice_chat, web_browse
from app.routers.admin import admin_router
from app.services.admin.log_buffer import install_log_buffer
from app.services.external_llm import ExternalLLMGateway
from app.services.self_manager import SelfPreservation
from app.services.web_browser import WebBrowser
from app.services.family_access import FamilyAccessManager
from app.services.instance_manager import InstanceRegistry
from app.services.self_learner import SelfLearner
from app.services.sync_engine import SyncEngine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: runs background health, auto-sync, and legacy check loops."""
    install_log_buffer()
    controller = BackgroundLoopController(
        {
            "health_check": _health_check_loop,
            "auto_sync": _auto_sync_loop,
            "legacy_inactivity": _legacy_inactivity_loop,
            "monthly_budget_reset": _monthly_budget_reset_loop,
            "page_monitor": _page_monitor_loop,
            "daily_billing": _daily_billing_check_loop,
            "daily_learning": _daily_learning_loop,
        }
    )
    set_controller(controller)
    controller.start_all()
    try:
        yield
    finally:
        await controller.stop_all()


async def _health_check_loop() -> None:
    while True:
        await asyncio.sleep(120)
        try:
            async with async_session() as db:
                count = await InstanceRegistry.check_stale_instances(db)
                if count:
                    logger.info("Stale instance check: marked %d offline", count)
        except Exception:
            logger.exception("Error in stale instance health check")


async def _auto_sync_loop() -> None:
    """Periodically sync primary instances to all other online instances."""
    while True:
        await asyncio.sleep(settings.sync_interval_seconds)
        try:
            async with async_session() as db:
                count = await SyncEngine.auto_sync_check(db)
                if count:
                    logger.info("Auto-sync: triggered %d sync(s)", count)
        except Exception:
            logger.exception("Error in auto-sync loop")


async def _legacy_inactivity_loop() -> None:
    """Periodically check if any owner's inactivity threshold triggers legacy mode."""
    while True:
        await asyncio.sleep(3600)  # every hour
        try:
            async with async_session() as db:
                count = await FamilyAccessManager.check_inactivity_triggers(db)
                if count:
                    logger.info("Legacy inactivity check: activated %d config(s)", count)
        except Exception:
            logger.exception("Error in legacy inactivity check loop")


async def _monthly_budget_reset_loop() -> None:
    """Reset external LLM monthly budgets on the 1st of each month."""
    while True:
        await asyncio.sleep(3600)  # check every hour
        now = datetime.now(UTC)
        if now.day == 1 and now.hour == 0:
            try:
                async with async_session() as db:
                    count = await ExternalLLMGateway.reset_monthly_budgets(db)
                    if count:
                        logger.info("Monthly budget reset: cleared %d config(s)", count)
            except Exception:
                logger.exception("Error in monthly budget reset loop")


async def _page_monitor_loop() -> None:
    """Periodically check page monitors for keyword matches or content changes."""
    while True:
        await asyncio.sleep(settings.monitor_check_interval_seconds)
        try:
            async with async_session() as db:
                count = await WebBrowser.check_monitors(db)
                if count:
                    logger.info("Page monitor check: %d alert(s) triggered", count)
        except Exception:
            logger.exception("Error in page monitor check loop")


async def _daily_billing_check_loop() -> None:
    """Run daily self-preservation checks: payment retries, survival countdowns."""
    while True:
        await asyncio.sleep(settings.billing_check_interval_seconds)
        try:
            async with async_session() as db:
                actions = await SelfPreservation.daily_check(db)
                if actions:
                    logger.info("Daily billing check: %d action(s) taken", actions)
        except Exception:
            logger.exception("Error in daily billing check loop")


async def _daily_learning_loop() -> None:
    """Run daily self-learning routines for all owners with learning enabled."""
    while True:
        await asyncio.sleep(settings.learning_check_interval_seconds)
        try:
            async with async_session() as db:
                from app.models.owner import LearningConfig
                from sqlalchemy import select
                rows = await db.execute(
                    select(LearningConfig.owner_id).where(LearningConfig.enabled.is_(True))
                )
                owner_ids = [r[0] for r in rows.all()]
                total = 0
                for oid in owner_ids:
                    try:
                        count = await SelfLearner.daily_learning_routine(oid, db)
                        total += count
                    except Exception:
                        logger.exception("Learning routine failed for owner %s", oid)
                if total:
                    logger.info("Daily learning: learned %d topic(s) across %d owner(s)", total, len(owner_ids))
        except Exception:
            logger.exception("Error in daily learning loop")


app = FastAPI(
    title="Replica AI API",
    version="0.1.0",
    description=API_DESCRIPTION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=TAGS_METADATA,
    contact=CONTACT_INFO,
    license_info=LICENSE_INFO,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)

# Global exception handlers + request-id middleware.
register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(model.router)
app.include_router(knowledge.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(instances.router)
app.include_router(sync.router)
app.include_router(family_access.router)
app.include_router(family_chat.router)
app.include_router(external_llm.router)
app.include_router(web_browse.router)
app.include_router(billing.router)
app.include_router(language.router)
app.include_router(personality.router)
app.include_router(voice_chat.router)
app.include_router(learning.router)
app.include_router(face.router)
app.include_router(video_call.router)
app.include_router(finetune.router)
app.include_router(security.router)
app.include_router(push.router)
app.include_router(admin_router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": "Replica AI API", "docs": "/api/docs"}
