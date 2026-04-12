"""Reusable retry decorators built on top of ``tenacity``.

Three canonical profiles:

- ``ollama_retry`` — 3 attempts, exponential backoff, for local LLM calls.
- ``external_llm_retry`` — 2 attempts, exponential backoff, for paid APIs.
- ``db_retry`` — 3 attempts on connection errors only, short backoff.

All decorators log each retry attempt and raise domain exceptions from
``app.core.exceptions`` when every attempt is exhausted.

Example
-------
    from app.core.retry import ollama_retry

    @ollama_retry
    async def generate(...):
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

import httpx
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import DatabaseError, ModelUnavailableError, UpstreamError

logger = logging.getLogger("replica.retry")

F = TypeVar("F", bound=Callable[..., Any])


# ─── Exception sets ──────────────────────────────────────────

# Transient HTTP/network errors worth retrying.
_HTTP_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
)

# DB errors worth retrying (connection-level only — not integrity errors).
_DB_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    OperationalError,
    DBAPIError,
)


# ─── Public decorators ───────────────────────────────────────


def ollama_retry(func: F) -> F:
    """Retry Ollama/local LLM calls with exponential backoff.

    On final failure, raises ``ModelUnavailableError`` so that routers
    and the global handler can return a friendly 503 to the client.
    """

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.retry_ollama_attempts),
                wait=wait_exponential(
                    multiplier=settings.retry_ollama_backoff_base,
                    max=settings.retry_ollama_backoff_max,
                ),
                retry=retry_if_exception_type(_HTTP_RETRY_EXCEPTIONS),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=False,
            ):
                with attempt:
                    return await func(*args, **kwargs)
        except RetryError as e:
            logger.error("Ollama call failed after %d attempts", settings.retry_ollama_attempts)
            raise ModelUnavailableError(
                "The local AI model is temporarily unreachable. Please try again in a minute.",
                details={"attempts": settings.retry_ollama_attempts},
            ) from e
        except httpx.HTTPStatusError as e:
            # 5xx from Ollama — don't keep pounding it, surface cleanly
            if 500 <= e.response.status_code < 600:
                raise ModelUnavailableError(
                    "The AI model returned an internal error. Please try again.",
                    details={"status": e.response.status_code},
                ) from e
            raise

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper  # type: ignore[return-value]


def external_llm_retry(func: F) -> F:
    """Retry external LLM (OpenAI, Anthropic, etc.) calls with exponential backoff.

    Two attempts only — paid APIs are expensive to hammer. On final
    failure, raises ``UpstreamError``.
    """

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.retry_external_llm_attempts),
                wait=wait_exponential(
                    multiplier=settings.retry_external_llm_backoff_base,
                    max=16.0,
                ),
                retry=retry_if_exception_type(_HTTP_RETRY_EXCEPTIONS),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=False,
            ):
                with attempt:
                    return await func(*args, **kwargs)
        except RetryError as e:
            logger.error(
                "External LLM call failed after %d attempts",
                settings.retry_external_llm_attempts,
            )
            raise UpstreamError(
                "The external AI provider is temporarily unavailable. "
                "You can retry later or fall back to the local model.",
                details={"attempts": settings.retry_external_llm_attempts},
            ) from e

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper  # type: ignore[return-value]


def db_retry(func: F) -> F:
    """Retry database operations on connection errors only.

    Does NOT retry IntegrityError, DataError, etc. — those indicate
    a logic problem, not a transient failure.
    """

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.retry_db_attempts),
                wait=wait_exponential(
                    multiplier=settings.retry_db_backoff_base,
                    max=4.0,
                ),
                retry=retry_if_exception_type(_DB_RETRY_EXCEPTIONS),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=False,
            ):
                with attempt:
                    return await func(*args, **kwargs)
        except RetryError as e:
            logger.error("DB call failed after %d attempts", settings.retry_db_attempts)
            raise DatabaseError(
                "The database is temporarily unavailable. Please try again.",
                details={"attempts": settings.retry_db_attempts},
            ) from e

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper  # type: ignore[return-value]


__all__ = ["ollama_retry", "external_llm_retry", "db_retry"]
