"""Shared pytest fixtures for the Replica AI API test suite.

This root conftest provides fixtures that are useful everywhere:

- ``mock_redis``: an ``AsyncMock`` stand-in for ``redis.asyncio.Redis``
- ``_db_setup`` (session, indirect): ensures the test Postgres database exists
  and has the latest schema. Tests opt in by depending on the ``client``
  fixture, which in turn depends on ``_db_setup``. Unit tests that want
  no database do not depend on the ``client`` fixture and therefore never
  trigger a database connection.
- ``client``: a FastAPI ``TestClient`` wired up to a fresh async engine and
  the mock Redis. Used by route-level integration tests.

Unit tests live in ``tests/unit`` and have their own ``conftest.py`` that
layers additional fully-mocked fixtures on top of these.

Integration tests live in ``tests/integration`` and add fixtures for
seeded data (owners, knowledge entries, etc).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

SYNC_DB_URL = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    "postgresql://postgres:postgres@localhost:5432/replica_ai_test",
)
ASYNC_DB_URL = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/replica_ai_test",
)
ADMIN_DB_URL = os.environ.get(
    "TEST_DATABASE_URL_ADMIN",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)


# ─── Database bootstrap helpers ─────────────────────────────


def _ensure_test_db() -> None:
    admin = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'replica_ai_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE replica_ai_test"))
    admin.dispose()


def _create_tables() -> None:
    # Import models lazily so that unit tests which never hit the database
    # don't pay the import cost (and don't need the SQLAlchemy metadata to
    # be fully configured to run).
    from app.models.chat import ConversationThread, Message  # noqa: F401
    from app.models.knowledge import KnowledgeEntry  # noqa: F401
    from app.models.voice import VerificationLog  # noqa: F401
    from app.models.identity import SuspicionEvent  # noqa: F401
    from app.models.owner import Base

    sync_engine = create_engine(SYNC_DB_URL)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()


def _truncate_tables() -> None:
    sync_engine = create_engine(SYNC_DB_URL)
    with sync_engine.connect() as conn:
        conn.execute(
            text(
                "TRUNCATE owners, model_instances, knowledge_entries, "
                "conversation_threads, messages, verification_logs, "
                "suspicion_events CASCADE"
            )
        )
        conn.commit()
    sync_engine.dispose()


# ─── Session fixture: lazy DB setup ─────────────────────────


@pytest.fixture(scope="session")
def _db_setup() -> Generator[None, None, None]:
    """Prepare the test Postgres database.

    Tests that need a real database (via the ``client`` fixture) will pull
    this in automatically. Unit tests skip it entirely.

    If Postgres is not reachable, the tests that depend on this fixture
    will be skipped with a clear message — pure unit tests still run.
    """
    try:
        _ensure_test_db()
        _create_tables()
    except OperationalError as exc:
        pytest.skip(f"Test database is not reachable: {exc}")
    yield


@pytest.fixture
def _clean_tables(_db_setup: None) -> Generator[None, None, None]:
    """Truncate all owned tables after each test that touches the DB."""
    yield
    try:
        _truncate_tables()
    except OperationalError:
        # Can't clean what we can't reach — downstream tests will be skipped.
        pass


# ─── Common mocks ───────────────────────────────────────────


@pytest.fixture()
def mock_redis() -> AsyncMock:
    """An ``AsyncMock`` Redis client pre-wired with the most-used methods."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=-2)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.ping = AsyncMock(return_value=True)
    redis.info = AsyncMock(return_value={})
    return redis


# ─── TestClient for route-level tests ──────────────────────


@pytest.fixture()
def client(mock_redis: AsyncMock, _clean_tables: None):
    """FastAPI ``TestClient`` with real DB + mocked Redis."""
    # Local imports so module collection doesn't fail when FastAPI isn't
    # available (e.g. during `pip install` inspection).
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    test_engine = create_async_engine(ASYNC_DB_URL, poolclass=NullPool)
    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()
