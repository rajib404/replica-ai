"""Sync flow integration tests.

The full sync engine has external HTTP dependencies on peer instances. We
patch the engine methods to return deterministic SyncLog-shaped objects so
we can validate the routing layer end-to-end.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest


@pytest.fixture
def fake_sync_engine(monkeypatch: pytest.MonkeyPatch):
    """Patch the SyncEngine instance bound to the sync router so it returns
    deterministic responses without contacting any other instance."""
    from app.routers import sync as sync_router

    fake_log = SimpleNamespace(
        id="sync-test-1",
        owner_id="WILL-BE-FILLED",
        sync_type="full",
        source_instance_id="src",
        target_instance_id="tgt",
        status="completed",
        entries_synced=42,
        conflicts_count=0,
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        completed_at=datetime(2026, 1, 1, 0, 0, 5),
        conflicts=[],
        error_message=None,
    )

    async def _full_sync(*, source_instance_id, target_instance_id, owner_id, db):
        fake_log.owner_id = owner_id
        fake_log.source_instance_id = source_instance_id
        fake_log.target_instance_id = target_instance_id
        return fake_log

    async def _incremental(*, source_instance_id, target_instance_id, owner_id, since, db):
        fake_log.owner_id = owner_id
        fake_log.sync_type = "incremental"
        fake_log.entries_synced = 7
        return fake_log

    async def _model_weights(*, source_instance_id, target_instance_id, owner_id, db):
        fake_log.owner_id = owner_id
        fake_log.sync_type = "model_weights"
        fake_log.entries_synced = 1
        return fake_log

    async def _get_status(sync_id, owner_id, db):
        if sync_id != fake_log.id:
            raise ValueError("Sync not found")
        fake_log.owner_id = owner_id
        return fake_log

    async def _history(*, owner_id, db, page, page_size, status_filter):
        return [], 0

    monkeypatch.setattr(sync_router.engine, "full_sync", _full_sync)
    monkeypatch.setattr(sync_router.engine, "incremental_sync", _incremental)
    monkeypatch.setattr(sync_router.engine, "sync_model_weights", _model_weights)
    monkeypatch.setattr(sync_router.engine, "get_sync_status", _get_status)
    monkeypatch.setattr(sync_router.engine, "get_sync_history", _history)

    yield fake_log


class TestSyncEndpoints:
    def test_start_full_sync(
        self, authed_owner: dict, fake_sync_engine
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        resp = client.post(
            "/api/sync/start",
            json={
                "source_instance_id": "instance-a",
                "target_instance_id": "instance-b",
                "sync_type": "full",
            },
            headers=headers,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["sync_id"] == "sync-test-1"
        assert body["status"] == "completed"
        assert "42" in body["message"]

    def test_start_incremental_sync_requires_since(
        self, authed_owner: dict, fake_sync_engine
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        # Missing 'since'
        resp = client.post(
            "/api/sync/start",
            json={
                "source_instance_id": "a",
                "target_instance_id": "b",
                "sync_type": "incremental",
            },
            headers=headers,
        )
        # Either 400 (missing since) or 422 (Pydantic validation)
        assert resp.status_code in (400, 422)

    def test_start_incremental_sync_with_since(
        self, authed_owner: dict, fake_sync_engine
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        resp = client.post(
            "/api/sync/start",
            json={
                "source_instance_id": "a",
                "target_instance_id": "b",
                "sync_type": "incremental",
                "since": "2026-01-01T00:00:00",
            },
            headers=headers,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "7" in body["message"]

    def test_unknown_sync_type_rejected(
        self, authed_owner: dict, fake_sync_engine
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        resp = client.post(
            "/api/sync/start",
            json={
                "source_instance_id": "a",
                "target_instance_id": "b",
                "sync_type": "telepathy",  # not a valid type
            },
            headers=headers,
        )
        assert resp.status_code in (400, 422)

    def test_get_sync_history_empty(
        self, authed_owner: dict, fake_sync_engine
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        resp = client.get("/api/sync/history", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["syncs"] == []

    def test_get_status_unknown_sync_returns_404(
        self, authed_owner: dict, fake_sync_engine
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        resp = client.get("/api/sync/status/no-such-sync", headers=headers)
        assert resp.status_code == 404

    def test_sync_endpoints_require_owner_role(self, client_with_ai) -> None:
        # No auth at all
        resp = client_with_ai.post(
            "/api/sync/start",
            json={
                "source_instance_id": "a",
                "target_instance_id": "b",
                "sync_type": "full",
            },
        )
        assert resp.status_code in (401, 403)
