"""Security middleware: response headers and rate limiting.

Adds the following protections:
- Strict-Transport-Security (HSTS)
- Content-Security-Policy
- X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- Per-IP token-bucket rate limiting with category-specific budgets:
  - /api/auth, /api/security/2fa → auth (tight)
  - /api/chat, /ws/* → chat
  - /api/knowledge, /api/voice, /api/verify → upload
  - /api/search, /api/browse → search
  - /api/billing, /api/external → billing
  - Everything else under /api/ → general API budget
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


# ─── Security headers ───────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard hardening headers to every response."""

    def __init__(self, app, csp: str | None = None) -> None:
        super().__init__(app)
        # Sane default CSP for an API server. Frontend serves its own CSP.
        self._csp = csp or (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; "
            "form-action 'none'"
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if not settings.security_headers_enabled:
            return response

        response.headers.setdefault("Content-Security-Policy", self._csp)
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={settings.hsts_max_age_seconds}; includeSubDomains; preload",
        )
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if settings.csp_report_uri:
            response.headers.setdefault(
                "Content-Security-Policy-Report-Only",
                f"{self._csp}; report-uri {settings.csp_report_uri}",
            )
        return response


# ─── Rate limiting ──────────────────────────────────────────


class _Bucket:
    __slots__ = ("tokens", "last_refill", "capacity", "refill_per_sec")

    def __init__(self, capacity: int, refill_per_sec: float) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


# Rate-limit category names
_CAT_AUTH = "auth"
_CAT_CHAT = "chat"
_CAT_UPLOAD = "upload"
_CAT_SEARCH = "search"
_CAT_BILLING = "billing"
_CAT_API = "api"


def _classify_path(path: str) -> str:
    """Map a request path to a rate-limit category."""
    if path.startswith("/api/auth") or path.startswith("/api/security/2fa"):
        return _CAT_AUTH
    if path.startswith("/ws/") or path.startswith("/api/chat"):
        return _CAT_CHAT
    if (
        path.startswith("/api/knowledge")
        or path.startswith("/api/voice")
        or path.startswith("/api/verify")
    ):
        return _CAT_UPLOAD
    if path.startswith("/api/search") or path.startswith("/api/browse"):
        return _CAT_SEARCH
    if path.startswith("/api/billing") or path.startswith("/api/external"):
        return _CAT_BILLING
    return _CAT_API


def _category_limit(cat: str) -> int:
    """Return the per-minute rate limit for a category."""
    if cat == _CAT_AUTH:
        return settings.rate_limit_auth_per_minute
    if cat == _CAT_CHAT:
        return settings.rate_limit_chat_per_minute
    if cat == _CAT_UPLOAD:
        return settings.rate_limit_upload_per_minute
    if cat == _CAT_SEARCH:
        return settings.rate_limit_search_per_minute
    if cat == _CAT_BILLING:
        return settings.rate_limit_billing_per_minute
    return settings.rate_limit_api_per_minute


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP token bucket with category-specific budgets.

    Each (IP, category) pair gets its own bucket with the capacity
    defined in settings. Categories: auth, chat, upload, search,
    billing, api (catch-all).
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        # Key: (ip, category) → _Bucket
        self._buckets: dict[tuple[str, str], _Bucket] = defaultdict(
            lambda: _Bucket(0, 0)  # placeholder; real init in _get_bucket
        )

    def _get_bucket(self, ip: str, cat: str) -> _Bucket:
        key = (ip, cat)
        bucket = self._buckets.get(key)
        if bucket is None:
            rate = _category_limit(cat)
            bucket = _Bucket(capacity=rate, refill_per_sec=rate / 60.0)
            self._buckets[key] = bucket
        return bucket

    def _client_ip(self, request: Request) -> str:
        # Honor X-Forwarded-For if present (single hop only)
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/") and not path.startswith("/ws/"):
            return await call_next(request)

        ip = self._client_ip(request)
        cat = _classify_path(path)
        bucket = self._get_bucket(ip, cat)
        limit = _category_limit(cat)

        if not bucket.take():
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down and try again.",
                    "limit_per_minute": limit,
                    "category": cat,
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
