"""In-memory ring buffer logging handler.

Installs a `logging.Handler` on the root logger that keeps the most recent
~N records in a `collections.deque` so the admin Logs page can render them
without any file I/O. Records are lost on restart by design.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from app.core.config import settings


class InMemoryLogHandler(logging.Handler):
    """Logging handler that retains recent records in memory."""

    def __init__(self, capacity: int) -> None:
        super().__init__(level=logging.INFO)
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._capacity = capacity
        self._lock = RLock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": datetime.fromtimestamp(record.created, UTC),
                "level": record.levelname,
                "logger_name": record.name,
                "message": record.getMessage(),
                "exc_info": self.formatter.formatException(record.exc_info)
                if (record.exc_info and self.formatter)
                else (logging.Formatter().formatException(record.exc_info) if record.exc_info else None),
            }
        except Exception:
            return
        with self._lock:
            self._buffer.append(entry)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._buffer)


_handler: InMemoryLogHandler | None = None


def install_log_buffer() -> InMemoryLogHandler:
    """Install the singleton handler on the root logger.

    Idempotent — calling more than once returns the existing instance.
    """
    global _handler
    if _handler is not None:
        return _handler
    handler = InMemoryLogHandler(capacity=settings.admin_log_buffer_size)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    _handler = handler
    return handler


def get_log_buffer() -> InMemoryLogHandler | None:
    return _handler


def query_logs(
    level: str | None = None,
    logger_substring: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> tuple[list[dict[str, Any]], int]:
    """Filter the buffer snapshot and return the most recent matches.

    Returns ``(items, total_in_buffer)``.
    """
    if _handler is None:
        return [], 0

    snapshot = _handler.snapshot()
    total = len(snapshot)

    level_norm = level.upper() if level and level.upper() != "ALL" else None
    logger_norm = logger_substring.lower() if logger_substring else None
    search_norm = search.lower() if search else None

    filtered: list[dict[str, Any]] = []
    for entry in reversed(snapshot):
        if level_norm and entry["level"] != level_norm:
            continue
        if logger_norm and logger_norm not in entry["logger_name"].lower():
            continue
        if search_norm and search_norm not in entry["message"].lower():
            continue
        filtered.append(entry)
        if len(filtered) >= limit:
            break
    return filtered, total
