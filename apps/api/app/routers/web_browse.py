"""Web browsing endpoints: browse URLs, search, monitors, history, domain rules."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.models.web_browse import (
    BrowseConfigResponse,
    BrowseHistoryResponse,
    BrowseLogEntry,
    BrowseResult,
    BrowseUrlRequest,
    CreateDomainRuleRequest,
    CreateMonitorRequest,
    DomainRuleListResponse,
    DomainRuleResponse,
    MonitorListResponse,
    MonitorResponse,
    SearchResponse,
    SearchResultItem,
    SearchWebRequest,
    UpdateBrowseConfigRequest,
    UpdateMonitorRequest,
)
from app.services.web_browser import WebBrowser

router = APIRouter(prefix="/api/browse", tags=["web-browse"])


# ─── Browse / Search ─────────────────────────────────────


@router.post("/url", response_model=BrowseResult)
async def browse_url(
    body: BrowseUrlRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> BrowseResult:
    result = await WebBrowser.browse(
        owner_id=auth.subject_id,
        url=body.url,
        db=db,
        summarize=body.summarize,
    )
    return BrowseResult(**result)


@router.post("/search", response_model=SearchResponse)
async def search_web(
    body: SearchWebRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    data = await WebBrowser.search_web(
        owner_id=auth.subject_id,
        query=body.query,
        db=db,
        max_results=body.max_results,
        summarize_top=body.summarize_top,
    )
    return SearchResponse(
        query=data["query"],
        results=[SearchResultItem(**r) for r in data["results"]],
        total=data["total"],
    )


# ─── History ─────────────────────────────────────────────


@router.get("/history", response_model=BrowseHistoryResponse)
async def get_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> BrowseHistoryResponse:
    data = await WebBrowser.get_history(
        auth.subject_id, db, limit=limit, offset=offset
    )
    return BrowseHistoryResponse(
        logs=[
            BrowseLogEntry(
                id=log.id,
                url=log.url,
                title=log.title,
                summary=log.summary,
                status_code=log.status_code,
                content_length=log.content_length,
                fetch_ms=log.fetch_ms,
                error=log.error,
                created_at=log.created_at,
            )
            for log in data["logs"]
        ],
        total=data["total"],
    )


# ─── Monitors CRUD ───────────────────────────────────────


@router.post("/monitors", status_code=201, response_model=MonitorResponse)
async def create_monitor(
    body: CreateMonitorRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> MonitorResponse:
    monitor = await WebBrowser.create_monitor(
        owner_id=auth.subject_id,
        url=body.url,
        keywords=body.keywords,
        interval_hours=body.interval_hours,
        db=db,
    )
    return _monitor_to_response(monitor)


@router.get("/monitors", response_model=MonitorListResponse)
async def list_monitors(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> MonitorListResponse:
    monitors = await WebBrowser.get_monitors(auth.subject_id, db)
    return MonitorListResponse(
        monitors=[_monitor_to_response(m) for m in monitors],
        total=len(monitors),
    )


@router.put("/monitors/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: str,
    body: UpdateMonitorRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> MonitorResponse:
    monitor = await WebBrowser.get_monitor(monitor_id, auth.subject_id, db)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found.")
    updates = body.model_dump(exclude_none=True)
    monitor = await WebBrowser.update_monitor(monitor, updates, db)
    return _monitor_to_response(monitor)


@router.delete("/monitors/{monitor_id}", status_code=204)
async def delete_monitor(
    monitor_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await WebBrowser.delete_monitor(monitor_id, auth.subject_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Monitor not found.")


# ─── Domain Rules ────────────────────────────────────────


@router.get("/domains", response_model=DomainRuleListResponse)
async def list_domain_rules(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> DomainRuleListResponse:
    rules = await WebBrowser.get_domain_rules(auth.subject_id, db)
    return DomainRuleListResponse(
        rules=[
            DomainRuleResponse(
                id=r.id,
                domain=r.domain,
                rule_type=r.rule_type.value,
                created_at=r.created_at,
            )
            for r in rules
        ],
        total=len(rules),
    )


@router.post("/domains", status_code=201, response_model=DomainRuleResponse)
async def create_domain_rule(
    body: CreateDomainRuleRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> DomainRuleResponse:
    rule = await WebBrowser.create_domain_rule(
        auth.subject_id, body.domain, body.rule_type, db
    )
    return DomainRuleResponse(
        id=rule.id,
        domain=rule.domain,
        rule_type=rule.rule_type.value,
        created_at=rule.created_at,
    )


@router.delete("/domains/{rule_id}", status_code=204)
async def delete_domain_rule(
    rule_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await WebBrowser.delete_domain_rule(rule_id, auth.subject_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Domain rule not found.")


# ─── Config ──────────────────────────────────────────────


@router.get("/config", response_model=BrowseConfigResponse)
async def get_browse_config(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> BrowseConfigResponse:
    config = await WebBrowser.ensure_browse_config(auth.subject_id, db)
    return BrowseConfigResponse(
        enabled=config.enabled,
        auto_summarize=config.auto_summarize,
        max_pages_per_day=config.max_pages_per_day,
    )


@router.put("/config", response_model=BrowseConfigResponse)
async def update_browse_config(
    body: UpdateBrowseConfigRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> BrowseConfigResponse:
    updates = body.model_dump(exclude_none=True)
    config = await WebBrowser.update_browse_config(auth.subject_id, updates, db)
    return BrowseConfigResponse(
        enabled=config.enabled,
        auto_summarize=config.auto_summarize,
        max_pages_per_day=config.max_pages_per_day,
    )


# ─── Helpers ─────────────────────────────────────────────


def _monitor_to_response(m) -> MonitorResponse:  # noqa: ANN001
    return MonitorResponse(
        id=m.id,
        url=m.url,
        keywords=m.keywords or [],
        interval_hours=m.interval_hours,
        status=m.status.value,
        last_checked_at=m.last_checked_at,
        last_triggered_at=m.last_triggered_at,
        trigger_reason=m.trigger_reason,
        check_count=m.check_count,
        created_at=m.created_at,
    )
