"""Web browsing service: fetch pages, search the web, monitor pages for changes."""

import hashlib
import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from cuid2 import cuid_wrapper
from sqlalchemy import delete, func as sa_func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import get_ai_client
from app.core.config import settings
from app.models.owner import (
    BrowseConfig,
    BrowseDomainRule,
    BrowseLog,
    DomainRuleType,
    MonitorStatus,
    PageMonitor,
)

logger = logging.getLogger(__name__)
generate_cuid = cuid_wrapper()

# ─── Default blocked domains ────────────────────────────

DEFAULT_BLOCKED_DOMAINS: set[str] = {
    # Adult content
    "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com",
    # Malware / phishing aggregators
    "malware-traffic-analysis.net",
    # Social login pages (prevent credential interception)
    "accounts.google.com", "login.microsoftonline.com",
    "facebook.com/login", "twitter.com/login",
    "auth0.com",
}


def _extract_domain(url: str) -> str:
    """Extract the registrable domain from a URL."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.hostname or ""
    # Strip www.
    if host.startswith("www."):
        host = host[4:]
    return host.lower()


def _extract_readable_content(html: str, url: str) -> tuple[str, str | None]:
    """Extract readable text and title from HTML.

    Uses trafilatura if available, falls back to a simple HTML tag stripper.
    """
    title: str | None = None

    # Try trafilatura first (best quality)
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            url=url,
            include_links=False,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        # Extract title separately
        metadata = trafilatura.extract_metadata(html, default_url=url)
        if metadata and metadata.title:
            title = metadata.title
        if extracted:
            return extracted, title
    except ImportError:
        pass

    # Fallback: BeautifulSoup
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines), title
    except ImportError:
        pass

    # Absolute fallback: regex-based tag stripping
    import re

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:50_000], title


# ─── WebBrowser class ───────────────────────────────────


class WebBrowser:
    """Stateless web browser with domain filtering, logging, and summarization."""

    # -- Domain rules --

    @staticmethod
    async def check_domain_allowed(
        owner_id: str, url: str, db: AsyncSession
    ) -> tuple[bool, str]:
        """Check if a URL's domain is allowed. Returns (allowed, reason)."""
        domain = _extract_domain(url)

        if not domain:
            return False, "Invalid URL."

        # Check global blocklist
        for blocked in DEFAULT_BLOCKED_DOMAINS:
            if domain == blocked or domain.endswith(f".{blocked}"):
                return False, f"Domain '{domain}' is blocked by default policy."

        # Check owner-specific rules
        result = await db.execute(
            select(BrowseDomainRule).where(
                BrowseDomainRule.owner_id == owner_id,
                BrowseDomainRule.domain == domain,
            )
        )
        rule = result.scalar_one_or_none()

        if rule:
            if rule.rule_type == DomainRuleType.block:
                return False, f"Domain '{domain}' is in your block list."
            # Explicit allow always passes
            return True, ""

        # Check if owner has any allow rules (whitelist mode)
        allow_count = await db.execute(
            select(sa_func.count(BrowseDomainRule.id)).where(
                BrowseDomainRule.owner_id == owner_id,
                BrowseDomainRule.rule_type == DomainRuleType.allow,
            )
        )
        if allow_count.scalar() and allow_count.scalar() > 0:
            # Owner uses allowlist mode — domain not in allowlist
            return False, f"Domain '{domain}' is not in your allow list."

        return True, ""

    @staticmethod
    async def get_browse_config(
        owner_id: str, db: AsyncSession
    ) -> BrowseConfig | None:
        result = await db.execute(
            select(BrowseConfig).where(BrowseConfig.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def ensure_browse_config(
        owner_id: str, db: AsyncSession
    ) -> BrowseConfig:
        config = await WebBrowser.get_browse_config(owner_id, db)
        if not config:
            config = BrowseConfig(
                id=generate_cuid(),
                owner_id=owner_id,
            )
            db.add(config)
            await db.commit()
            await db.refresh(config)
        return config

    @staticmethod
    async def update_browse_config(
        owner_id: str, updates: dict, db: AsyncSession
    ) -> BrowseConfig:
        config = await WebBrowser.ensure_browse_config(owner_id, db)
        for key, value in updates.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        await db.commit()
        await db.refresh(config)
        return config

    # -- Core browse --

    @staticmethod
    async def browse(
        owner_id: str,
        url: str,
        db: AsyncSession,
        summarize: bool = True,
    ) -> dict:
        """Fetch a URL, extract content, optionally summarize. Returns BrowseResult dict."""
        import httpx

        # Ensure https
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Check config
        config = await WebBrowser.ensure_browse_config(owner_id, db)
        if not config.enabled:
            return _make_error_result(url, "Web browsing is disabled.")

        # Check daily limit
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        count_result = await db.execute(
            select(sa_func.count(BrowseLog.id)).where(
                BrowseLog.owner_id == owner_id,
                BrowseLog.created_at >= today_start,
            )
        )
        today_count = count_result.scalar() or 0
        if today_count >= config.max_pages_per_day:
            return _make_error_result(url, "Daily browsing limit reached.")

        # Domain check
        allowed, reason = await WebBrowser.check_domain_allowed(owner_id, url, db)
        if not allowed:
            return _make_error_result(url, reason)

        # Fetch
        start_ms = int(time.time() * 1000)
        log_id = generate_cuid()

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(float(settings.browse_timeout_seconds)),
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": settings.browse_user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                    },
                )

            fetch_ms = int(time.time() * 1000) - start_ms
            status_code = resp.status_code

            if resp.status_code >= 400:
                log = _create_log(
                    log_id, owner_id, url, None, None, None,
                    status_code, f"HTTP {status_code}", 0, fetch_ms,
                )
                db.add(log)
                await db.commit()
                return _log_to_result(log)

            # Check content size
            content = resp.text
            content_bytes = len(resp.content)
            if content_bytes > settings.browse_max_page_bytes:
                content = content[: settings.browse_max_page_bytes]

            # Extract readable content
            text, title = _extract_readable_content(content, url)
            # Trim to reasonable size for storage/summarization
            if len(text) > 100_000:
                text = text[:100_000]

            # Summarize
            summary: str | None = None
            if summarize and config.auto_summarize and text:
                try:
                    ai_client = get_ai_client()
                    summary = await ai_client.summarize(text[:10_000], max_tokens=512)
                except Exception:
                    logger.warning("Failed to summarize page %s", url, exc_info=True)

            log = _create_log(
                log_id, owner_id, url, title, text, summary,
                status_code, None, len(text), fetch_ms,
            )
            db.add(log)
            await db.commit()
            return _log_to_result(log)

        except httpx.TimeoutException:
            fetch_ms = int(time.time() * 1000) - start_ms
            log = _create_log(
                log_id, owner_id, url, None, None, None,
                None, "Request timed out", 0, fetch_ms,
            )
            db.add(log)
            await db.commit()
            return _log_to_result(log)

        except httpx.HTTPError as exc:
            fetch_ms = int(time.time() * 1000) - start_ms
            log = _create_log(
                log_id, owner_id, url, None, None, None,
                None, str(exc)[:500], 0, fetch_ms,
            )
            db.add(log)
            await db.commit()
            return _log_to_result(log)

    # -- Web search --

    @staticmethod
    async def search_web(
        owner_id: str,
        query: str,
        db: AsyncSession,
        max_results: int = 10,
        summarize_top: int = 0,
    ) -> dict:
        """Search the web using DuckDuckGo. Returns search results."""
        config = await WebBrowser.ensure_browse_config(owner_id, db)
        if not config.enabled:
            return {"query": query, "results": [], "total": 0}

        results = await _duckduckgo_search(query, max_results)

        # Optionally summarize top N results
        if summarize_top > 0:
            for i, result in enumerate(results[:summarize_top]):
                try:
                    browse_result = await WebBrowser.browse(
                        owner_id, result["url"], db, summarize=True
                    )
                    if browse_result.get("summary"):
                        results[i]["summary"] = browse_result["summary"]
                except Exception:
                    logger.warning(
                        "Failed to summarize search result %s", result["url"],
                        exc_info=True,
                    )

        return {
            "query": query,
            "results": results,
            "total": len(results),
        }

    # -- Page monitors --

    @staticmethod
    async def create_monitor(
        owner_id: str,
        url: str,
        keywords: list[str],
        interval_hours: float,
        db: AsyncSession,
    ) -> PageMonitor:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        monitor = PageMonitor(
            id=generate_cuid(),
            owner_id=owner_id,
            url=url,
            keywords=keywords if keywords else None,
            interval_hours=interval_hours,
        )
        db.add(monitor)
        await db.commit()
        await db.refresh(monitor)
        return monitor

    @staticmethod
    async def get_monitors(
        owner_id: str, db: AsyncSession
    ) -> list[PageMonitor]:
        result = await db.execute(
            select(PageMonitor)
            .where(PageMonitor.owner_id == owner_id)
            .order_by(PageMonitor.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_monitor(
        monitor_id: str, owner_id: str, db: AsyncSession
    ) -> PageMonitor | None:
        result = await db.execute(
            select(PageMonitor).where(
                PageMonitor.id == monitor_id,
                PageMonitor.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_monitor(
        monitor: PageMonitor, updates: dict, db: AsyncSession
    ) -> PageMonitor:
        for key, value in updates.items():
            if value is not None and hasattr(monitor, key):
                if key == "status":
                    monitor.status = MonitorStatus(value)
                else:
                    setattr(monitor, key, value)
        await db.commit()
        await db.refresh(monitor)
        return monitor

    @staticmethod
    async def delete_monitor(
        monitor_id: str, owner_id: str, db: AsyncSession
    ) -> bool:
        monitor = await WebBrowser.get_monitor(monitor_id, owner_id, db)
        if not monitor:
            return False
        await db.delete(monitor)
        await db.commit()
        return True

    # -- Monitor check (called by background task) --

    @staticmethod
    async def check_monitors(db: AsyncSession) -> int:
        """Check all active monitors that are due. Returns count of triggered alerts."""
        now = datetime.now(UTC).replace(tzinfo=None)
        result = await db.execute(
            select(PageMonitor).where(
                PageMonitor.status == MonitorStatus.active,
            )
        )
        monitors = list(result.scalars().all())
        triggered = 0

        for monitor in monitors:
            # Check if due
            if monitor.last_checked_at:
                next_check = monitor.last_checked_at.timestamp() + (monitor.interval_hours * 3600)
                if now.timestamp() < next_check:
                    continue

            try:
                trigger_reason = await _check_single_monitor(monitor, db)
                monitor.last_checked_at = now
                monitor.check_count += 1
                if trigger_reason:
                    monitor.status = MonitorStatus.triggered
                    monitor.last_triggered_at = now
                    monitor.trigger_reason = trigger_reason
                    triggered += 1
                    logger.info(
                        "Monitor %s triggered: %s", monitor.id, trigger_reason
                    )
            except Exception:
                logger.warning("Failed to check monitor %s", monitor.id, exc_info=True)

        await db.commit()
        return triggered

    # -- Domain rules CRUD --

    @staticmethod
    async def get_domain_rules(
        owner_id: str, db: AsyncSession
    ) -> list[BrowseDomainRule]:
        result = await db.execute(
            select(BrowseDomainRule)
            .where(BrowseDomainRule.owner_id == owner_id)
            .order_by(BrowseDomainRule.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_domain_rule(
        owner_id: str, domain: str, rule_type: str, db: AsyncSession
    ) -> BrowseDomainRule:
        domain = _extract_domain(domain) or domain.lower().strip()
        rule = BrowseDomainRule(
            id=generate_cuid(),
            owner_id=owner_id,
            domain=domain,
            rule_type=DomainRuleType(rule_type),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def delete_domain_rule(
        rule_id: str, owner_id: str, db: AsyncSession
    ) -> bool:
        result = await db.execute(
            select(BrowseDomainRule).where(
                BrowseDomainRule.id == rule_id,
                BrowseDomainRule.owner_id == owner_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            return False
        await db.delete(rule)
        await db.commit()
        return True

    # -- Browse history --

    @staticmethod
    async def get_history(
        owner_id: str, db: AsyncSession, limit: int = 50, offset: int = 0
    ) -> dict:
        total_result = await db.execute(
            select(sa_func.count(BrowseLog.id)).where(
                BrowseLog.owner_id == owner_id
            )
        )
        total = total_result.scalar() or 0

        result = await db.execute(
            select(BrowseLog)
            .where(BrowseLog.owner_id == owner_id)
            .order_by(BrowseLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        logs = list(result.scalars().all())

        return {"logs": logs, "total": total}


# ─── Internal helpers ────────────────────────────────────


def _make_error_result(url: str, error: str) -> dict:
    return {
        "id": generate_cuid(),
        "url": url,
        "title": None,
        "content": None,
        "summary": None,
        "status_code": None,
        "content_length": 0,
        "fetch_ms": 0,
        "error": error,
    }


def _create_log(
    log_id: str,
    owner_id: str,
    url: str,
    title: str | None,
    content_text: str | None,
    summary: str | None,
    status_code: int | None,
    error: str | None,
    content_length: int,
    fetch_ms: int,
) -> BrowseLog:
    return BrowseLog(
        id=log_id,
        owner_id=owner_id,
        url=url,
        title=title,
        content_text=content_text,
        summary=summary,
        status_code=status_code,
        error=error,
        content_length=content_length,
        fetch_ms=fetch_ms,
    )


def _log_to_result(log: BrowseLog) -> dict:
    return {
        "id": log.id,
        "url": log.url,
        "title": log.title,
        "content": log.content_text,
        "summary": log.summary,
        "status_code": log.status_code,
        "content_length": log.content_length,
        "fetch_ms": log.fetch_ms,
        "error": log.error,
    }


async def _duckduckgo_search(query: str, max_results: int) -> list[dict]:
    """Search DuckDuckGo using the HTML endpoint (no API key needed)."""
    import httpx

    results: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            # Use the DuckDuckGo lite HTML endpoint
            resp = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers={
                    "User-Agent": settings.browse_user_agent,
                },
            )
            resp.raise_for_status()

            # Parse results from HTML
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(resp.text, "html.parser")
                # DuckDuckGo lite returns results in table rows
                links = soup.find_all("a", class_="result-link")
                if not links:
                    # Try alternate selector for lite results
                    links = soup.select("table:nth-of-type(n+2) a[href^='http']")

                snippets = soup.find_all("td", class_="result-snippet")

                for i, link in enumerate(links[:max_results]):
                    href = link.get("href", "")
                    title = link.get_text(strip=True)
                    snippet = ""
                    if i < len(snippets):
                        snippet = snippets[i].get_text(strip=True)
                    if href and title:
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": snippet,
                            "summary": None,
                        })
            except ImportError:
                # Without bs4 we can't parse HTML search results
                logger.warning("BeautifulSoup not installed, search parsing limited")

    except Exception:
        logger.warning("DuckDuckGo search failed for query: %s", query, exc_info=True)

    # If HTML parsing failed or returned nothing, try the JSON API
    if not results:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": "1"},
                    headers={"User-Agent": settings.browse_user_agent},
                )
                resp.raise_for_status()
                data = resp.json()

                # Abstract result
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading", query),
                        "url": data.get("AbstractURL", ""),
                        "snippet": data["AbstractText"],
                        "summary": None,
                    })

                # Related topics
                for topic in data.get("RelatedTopics", [])[:max_results]:
                    if isinstance(topic, dict) and topic.get("FirstURL"):
                        results.append({
                            "title": topic.get("Text", "")[:100],
                            "url": topic["FirstURL"],
                            "snippet": topic.get("Text", ""),
                            "summary": None,
                        })
        except Exception:
            logger.warning("DuckDuckGo JSON API also failed", exc_info=True)

    return results[:max_results]


async def _check_single_monitor(monitor: PageMonitor, db: AsyncSession) -> str | None:
    """Check a single page monitor. Returns trigger reason or None."""
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(settings.browse_timeout_seconds)),
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                monitor.url,
                headers={"User-Agent": settings.browse_user_agent},
            )
            resp.raise_for_status()
            content = resp.text
    except Exception as exc:
        logger.warning("Monitor %s fetch failed: %s", monitor.id, exc)
        return None

    # Extract readable text
    text, _ = _extract_readable_content(content, monitor.url)

    # Check keywords
    keywords = monitor.keywords or []
    if keywords:
        text_lower = text.lower()
        found = [kw for kw in keywords if kw.lower() in text_lower]
        if found:
            return f"Keywords found: {', '.join(found)}"

    # Check content change via hash
    content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    if monitor.last_content_hash and monitor.last_content_hash != content_hash:
        monitor.last_content_hash = content_hash
        return "Page content changed significantly."

    # Update hash if first check
    if not monitor.last_content_hash:
        monitor.last_content_hash = content_hash

    return None
