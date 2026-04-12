"""In-process controller for the lifespan background loops.

Wrapping the loops behind one controller makes the admin maintenance
endpoint able to cancel and relaunch them without restarting the
process.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

logger = logging.getLogger(__name__)

LoopFactory = Callable[[], Awaitable[None]]


class BackgroundLoopController:
    """Owns the lifecycle of named background asyncio tasks."""

    def __init__(self, factories: dict[str, LoopFactory]) -> None:
        self._factories: dict[str, LoopFactory] = dict(factories)
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def names(self) -> list[str]:
        return list(self._factories)

    @property
    def running_names(self) -> list[str]:
        return [name for name, task in self._tasks.items() if not task.done()]

    def start_all(self) -> list[str]:
        for name, factory in self._factories.items():
            existing = self._tasks.get(name)
            if existing is not None and not existing.done():
                continue
            self._tasks[name] = asyncio.create_task(factory(), name=name)
        return list(self._tasks)

    async def stop_all(self) -> list[str]:
        names = list(self._tasks)
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        return names

    async def restart_all(self) -> list[str]:
        await self.stop_all()
        return self.start_all()


_controller: BackgroundLoopController | None = None


def set_controller(controller: BackgroundLoopController) -> None:
    """Register the process-wide controller (called from main.lifespan)."""
    global _controller
    _controller = controller


def get_controller() -> BackgroundLoopController | None:
    return _controller
