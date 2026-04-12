"""Global exception handlers for the FastAPI application.

Translates every exception into a consistent JSON envelope::

    {
        "error": {
            "code": "...",
            "message": "...",
            "details": {...}
        }
    }

All errors are logged with request context (IP, user_id if available,
endpoint, method, request_id, timestamp).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AppError,
    AuthError,
    ConflictError,
    DatabaseError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)

logger = logging.getLogger("replica.errors")


# ─── Context builders ────────────────────────────────────────


def _request_context(request: Request) -> dict[str, Any]:
    """Build a structured context dict for error logging.

    We never put secrets (Authorization header, cookies) in this dict.
    """
    client_ip = "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        client_ip = fwd.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host

    # user_id is injected by the auth dependency on request.state when available
    user_id = getattr(request.state, "user_id", None)
    request_id = getattr(request.state, "request_id", None)

    return {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "client_ip": client_ip,
        "user_id": user_id,
        "user_agent": request.headers.get("user-agent", ""),
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _envelope(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


def _log(level: str, exc: Exception, ctx: dict[str, Any]) -> None:
    payload = {"error_type": type(exc).__name__, "error_msg": str(exc), **ctx}
    if level == "error":
        logger.error("request failed: %s", payload, exc_info=True)
    else:
        logger.warning("request error: %s", payload)


# ─── Handler implementations ─────────────────────────────────


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    ctx = _request_context(request)
    _log(exc.log_level, exc, ctx)
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, exc.details),
        headers={"X-Request-Id": ctx.get("request_id") or ""},
    )


async def _http_exception_handler(
    request: Request, exc: HTTPException | StarletteHTTPException
) -> JSONResponse:
    ctx = _request_context(request)
    status_code = exc.status_code
    code_map = {
        400: "BAD_REQUEST",
        401: "AUTH_FAILED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        502: "UPSTREAM_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(status_code, f"HTTP_{status_code}")

    detail = exc.detail
    message: str
    details: dict[str, Any] = {}
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or code)
        details = {k: v for k, v in detail.items() if k not in ("message", "detail")}
    else:
        message = str(detail) if detail is not None else code

    level = "error" if status_code >= 500 else "warning"
    _log(level, exc, ctx)

    return JSONResponse(
        status_code=status_code,
        content=_envelope(code, message, details),
        headers={"X-Request-Id": ctx.get("request_id") or ""},
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    ctx = _request_context(request)
    _log("warning", exc, ctx)
    errors = [
        {
            "loc": list(err.get("loc", [])),
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            "VALIDATION_ERROR",
            "One or more fields failed validation.",
            {"fields": errors},
        ),
        headers={"X-Request-Id": ctx.get("request_id") or ""},
    )


async def _integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    ctx = _request_context(request)
    _log("warning", exc, ctx)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=_envelope(
            "CONFLICT",
            "The request conflicts with an existing record.",
            {},
        ),
        headers={"X-Request-Id": ctx.get("request_id") or ""},
    )


async def _sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    ctx = _request_context(request)
    _log("error", exc, ctx)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "DATABASE_ERROR",
            "A database error occurred. Please try again.",
            {},
        ),
        headers={"X-Request-Id": ctx.get("request_id") or ""},
    )


async def _catchall_handler(request: Request, exc: Exception) -> JSONResponse:
    ctx = _request_context(request)
    _log("error", exc, ctx)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "INTERNAL_ERROR",
            "An unexpected error occurred. Please try again or contact support.",
            {"request_id": ctx.get("request_id")} if ctx.get("request_id") else {},
        ),
        headers={"X-Request-Id": ctx.get("request_id") or ""},
    )


# ─── Request-id middleware ───────────────────────────────────


async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Assigns a UUID to every request and echoes it in the response header.

    Stored on ``request.state.request_id`` so downstream handlers and the
    global exception handler can include it in structured logs.
    """
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers.setdefault("X-Request-Id", request_id)
    return response


# ─── Registration ────────────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers + the request-id middleware.

    Call this from ``main.py`` after the FastAPI app is constructed.
    """
    # Order matters: specific subclasses first, then base AppError, then
    # HTTPException, then catch-all Exception.
    app.add_exception_handler(AuthError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ForbiddenError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(NotFoundError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ConflictError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(UpstreamError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DatabaseError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]

    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, _integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(SQLAlchemyError, _sqlalchemy_error_handler)  # type: ignore[arg-type]

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, _http_exception_handler)  # type: ignore[arg-type]

    app.add_exception_handler(Exception, _catchall_handler)

    # Request-id middleware for trace correlation.
    app.middleware("http")(request_id_middleware)
