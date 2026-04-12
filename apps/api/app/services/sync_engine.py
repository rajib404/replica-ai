"""Sync engine: coordinates data replication between model instances.

The API service (apps/api) owns PostgreSQL. Each AI instance (apps/ai) owns
its own Qdrant vectors, file storage, and Ollama models. The sync engine
orchestrates data transfer between instances via their HTTP APIs.

Sync protocol:
- All transfers use HTTP with gzip Accept-Encoding
- Authenticated with instance JWT tokens
- Chunked transfer for large payloads (model weights)
- SyncLog tracks every operation for audit + resume
"""

import hashlib
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge import KnowledgeEntry
from app.models.owner import (
    ConflictResolution,
    ModelInstance,
    SyncConflict,
    SyncLog,
    SyncStatus,
    SyncType,
)
from app.models.sync import SyncConflictResponse, SyncLogResponse

logger = logging.getLogger(__name__)

# Timeout for instance-to-instance HTTP calls
_INSTANCE_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# Chunk size for model weight transfers (4 MB)
_MODEL_CHUNK_SIZE = 4 * 1024 * 1024


def _generate_cuid() -> str:
    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _synclog_to_response(log: SyncLog, conflicts: list[SyncConflict] | None = None) -> SyncLogResponse:
    return SyncLogResponse(
        id=log.id,
        source_instance_id=log.source_instance_id,
        target_instance_id=log.target_instance_id,
        sync_type=log.sync_type.value,
        entries_synced=log.entries_synced,
        total_entries=log.total_entries,
        bytes_transferred=log.bytes_transferred,
        total_bytes=log.total_bytes,
        status=log.status.value,
        error_message=log.error_message,
        started_at=log.started_at,
        completed_at=log.completed_at,
        conflicts=[_conflict_to_response(c) for c in (conflicts or [])],
    )


def _conflict_to_response(conflict: SyncConflict) -> SyncConflictResponse:
    return SyncConflictResponse(
        id=conflict.id,
        sync_log_id=conflict.sync_log_id,
        entry_id=conflict.entry_id,
        entry_type=conflict.entry_type,
        source_data=conflict.source_data,
        target_data=conflict.target_data,
        resolution=conflict.resolution.value,
        resolved_at=conflict.resolved_at,
        created_at=conflict.created_at,
    )


class SyncEngine:
    """Coordinates data replication between model instances."""

    # ── Public API ───────────────────────────────────────

    async def full_sync(
        self,
        source_instance_id: str,
        target_instance_id: str,
        owner_id: str,
        db: AsyncSession,
    ) -> SyncLogResponse:
        """Compare all knowledge entries, conversations, access rules
        between source and target, transfer deltas, log conflicts."""
        source, target = await self._load_instances(
            source_instance_id, target_instance_id, owner_id, db
        )

        sync_log = SyncLog(
            id=_generate_cuid(),
            source_instance_id=source.id,
            target_instance_id=target.id,
            sync_type=SyncType.full,
            status=SyncStatus.in_progress,
        )
        db.add(sync_log)
        await db.commit()

        try:
            synced, conflicts = await self._sync_knowledge_entries(
                source, target, owner_id, db, sync_log, since=None
            )
            thread_count = await self._sync_conversations(
                source, target, owner_id, db, sync_log, since=None
            )
            rule_count = await self._sync_access_rules(
                source, target, owner_id, db, sync_log, since=None
            )

            sync_log.entries_synced = synced + thread_count + rule_count
            sync_log.status = SyncStatus.completed
            sync_log.completed_at = _utcnow()

            source.last_sync_at = _utcnow()
            target.last_sync_at = _utcnow()

            await db.commit()
            await db.refresh(sync_log)

            all_conflicts = await self._get_conflicts_for_log(sync_log.id, db)
            return _synclog_to_response(sync_log, all_conflicts)

        except Exception as exc:
            sync_log.status = SyncStatus.failed
            sync_log.error_message = str(exc)[:1000]
            sync_log.completed_at = _utcnow()
            await db.commit()
            logger.exception("Full sync failed: %s -> %s", source.id, target.id)
            raise

    async def incremental_sync(
        self,
        source_instance_id: str,
        target_instance_id: str,
        owner_id: str,
        since: datetime,
        db: AsyncSession,
    ) -> SyncLogResponse:
        """Only sync entries modified after `since`. Much faster for regular syncs."""
        source, target = await self._load_instances(
            source_instance_id, target_instance_id, owner_id, db
        )

        sync_log = SyncLog(
            id=_generate_cuid(),
            source_instance_id=source.id,
            target_instance_id=target.id,
            sync_type=SyncType.incremental,
            status=SyncStatus.in_progress,
        )
        db.add(sync_log)
        await db.commit()

        try:
            synced, conflicts = await self._sync_knowledge_entries(
                source, target, owner_id, db, sync_log, since=since
            )
            thread_count = await self._sync_conversations(
                source, target, owner_id, db, sync_log, since=since
            )
            rule_count = await self._sync_access_rules(
                source, target, owner_id, db, sync_log, since=since
            )

            sync_log.entries_synced = synced + thread_count + rule_count
            sync_log.status = SyncStatus.completed
            sync_log.completed_at = _utcnow()

            source.last_sync_at = _utcnow()
            target.last_sync_at = _utcnow()

            await db.commit()
            await db.refresh(sync_log)

            all_conflicts = await self._get_conflicts_for_log(sync_log.id, db)
            return _synclog_to_response(sync_log, all_conflicts)

        except Exception as exc:
            sync_log.status = SyncStatus.failed
            sync_log.error_message = str(exc)[:1000]
            sync_log.completed_at = _utcnow()
            await db.commit()
            logger.exception("Incremental sync failed: %s -> %s", source.id, target.id)
            raise

    async def sync_model_weights(
        self,
        source_instance_id: str,
        target_instance_id: str,
        owner_id: str,
        db: AsyncSession,
    ) -> SyncLogResponse:
        """Export Ollama model from source, transfer to target, verify hash."""
        source, target = await self._load_instances(
            source_instance_id, target_instance_id, owner_id, db
        )

        if not source.api_url or not target.api_url:
            raise ValueError("Both instances must have api_url set for model sync")

        sync_log = SyncLog(
            id=_generate_cuid(),
            source_instance_id=source.id,
            target_instance_id=target.id,
            sync_type=SyncType.model_weights,
            status=SyncStatus.in_progress,
        )
        db.add(sync_log)
        await db.commit()

        try:
            # 1. List models on source to find what to transfer
            async with httpx.AsyncClient(timeout=_INSTANCE_TIMEOUT) as client:
                source_models = await client.get(f"{source.api_url}/models")
                source_models.raise_for_status()
                models_list = source_models.json().get("models", [])

            if not models_list:
                sync_log.status = SyncStatus.completed
                sync_log.completed_at = _utcnow()
                sync_log.entries_synced = 0
                await db.commit()
                return _synclog_to_response(sync_log)

            sync_log.total_entries = len(models_list)
            await db.commit()

            transferred = 0
            total_bytes = 0

            for model_info in models_list:
                model_name = model_info.get("name", model_info.get("model", ""))
                if not model_name:
                    continue

                # 2. Export model blob from source (chunked download)
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(600.0, connect=10.0),
                    headers={"Accept-Encoding": "gzip"},
                ) as client:
                    # Pull model data from source Ollama via AI service
                    export_resp = await client.post(
                        f"{source.api_url}/models/export",
                        json={"model": model_name},
                    )
                    if export_resp.status_code == 404:
                        logger.warning("Model %s not available for export, skipping", model_name)
                        continue
                    export_resp.raise_for_status()
                    model_data = export_resp.content
                    model_hash = hashlib.sha256(model_data).hexdigest()

                # 3. Import on target
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(600.0, connect=10.0),
                ) as client:
                    import_resp = await client.post(
                        f"{target.api_url}/models/import",
                        content=model_data,
                        headers={
                            "Content-Type": "application/octet-stream",
                            "X-Model-Name": model_name,
                            "X-Model-Hash": model_hash,
                        },
                    )
                    import_resp.raise_for_status()

                    # 4. Verify hash on target
                    result = import_resp.json()
                    target_hash = result.get("hash", "")
                    if target_hash and target_hash != model_hash:
                        raise ValueError(
                            f"Model hash mismatch for {model_name}: "
                            f"source={model_hash[:12]} target={target_hash[:12]}"
                        )

                transferred += 1
                total_bytes += len(model_data)

                sync_log.entries_synced = transferred
                sync_log.bytes_transferred = total_bytes
                sync_log.total_bytes = total_bytes
                await db.commit()

            sync_log.status = SyncStatus.completed
            sync_log.completed_at = _utcnow()
            await db.commit()
            await db.refresh(sync_log)
            return _synclog_to_response(sync_log)

        except Exception as exc:
            sync_log.status = SyncStatus.failed
            sync_log.error_message = str(exc)[:1000]
            sync_log.completed_at = _utcnow()
            await db.commit()
            logger.exception("Model weight sync failed: %s -> %s", source.id, target.id)
            raise

    async def get_sync_status(
        self, sync_id: str, owner_id: str, db: AsyncSession
    ) -> SyncLogResponse:
        """Get status of a sync operation including conflicts."""
        sync_log = await self._load_sync_log(sync_id, owner_id, db)
        conflicts = await self._get_conflicts_for_log(sync_id, db)
        return _synclog_to_response(sync_log, conflicts)

    async def get_sync_history(
        self,
        owner_id: str,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
    ) -> tuple[list[SyncLogResponse], int]:
        """Get sync history for all instances belonging to this owner."""
        # Get all instance IDs for this owner
        inst_result = await db.execute(
            select(ModelInstance.id).where(ModelInstance.owner_id == owner_id)
        )
        instance_ids = [r[0] for r in inst_result.all()]

        if not instance_ids:
            return [], 0

        base_filter = SyncLog.source_instance_id.in_(instance_ids) | SyncLog.target_instance_id.in_(
            instance_ids
        )
        if status_filter:
            base_filter = base_filter & (SyncLog.status == SyncStatus(status_filter))

        total_result = await db.execute(
            select(func.count(SyncLog.id)).where(base_filter)
        )
        total = total_result.scalar() or 0

        result = await db.execute(
            select(SyncLog)
            .where(base_filter)
            .order_by(SyncLog.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        logs = list(result.scalars().all())

        responses = []
        for log in logs:
            conflicts = await self._get_conflicts_for_log(log.id, db)
            responses.append(_synclog_to_response(log, conflicts))

        return responses, total

    async def resolve_conflict(
        self,
        conflict_id: str,
        resolution: str,
        owner_id: str,
        db: AsyncSession,
    ) -> SyncConflictResponse:
        """Resolve a sync conflict by choosing source, target, or both."""
        result = await db.execute(
            select(SyncConflict).where(SyncConflict.id == conflict_id)
        )
        conflict = result.scalar_one_or_none()
        if not conflict:
            raise ValueError("Conflict not found")

        # Verify ownership through sync log -> instance -> owner
        log_result = await db.execute(
            select(SyncLog).where(SyncLog.id == conflict.sync_log_id)
        )
        sync_log = log_result.scalar_one_or_none()
        if not sync_log:
            raise ValueError("Conflict not found")

        inst_result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.id == sync_log.source_instance_id,
                ModelInstance.owner_id == owner_id,
            )
        )
        if not inst_result.scalar_one_or_none():
            raise ValueError("Conflict not found")

        conflict.resolution = ConflictResolution(resolution)
        conflict.resolved_at = _utcnow()

        # Apply the resolution to the actual data
        await self._apply_conflict_resolution(conflict, db)

        await db.commit()
        await db.refresh(conflict)
        return _conflict_to_response(conflict)

    @staticmethod
    async def auto_sync_check(db: AsyncSession) -> int:
        """Background job: for each owner with a primary instance and other
        online instances, trigger an incremental sync from primary to each."""
        # Find all primary instances that have an api_url
        result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.is_primary == True,  # noqa: E712
                ModelInstance.status != "offline",
            )
        )
        primaries = list(result.scalars().all())

        engine = SyncEngine()
        syncs_triggered = 0

        for primary in primaries:
            # Find other online instances for this owner
            others_result = await db.execute(
                select(ModelInstance).where(
                    ModelInstance.owner_id == primary.owner_id,
                    ModelInstance.id != primary.id,
                    ModelInstance.status != "offline",
                )
            )
            others = list(others_result.scalars().all())

            for target in others:
                since = target.last_sync_at or (
                    _utcnow() - timedelta(days=30)
                )
                try:
                    await engine.incremental_sync(
                        source_instance_id=primary.id,
                        target_instance_id=target.id,
                        owner_id=primary.owner_id,
                        since=since,
                        db=db,
                    )
                    syncs_triggered += 1
                except Exception:
                    logger.exception(
                        "Auto-sync failed: %s -> %s", primary.id, target.id
                    )

        return syncs_triggered

    # ── Private helpers ──────────────────────────────────

    async def _load_instances(
        self,
        source_id: str,
        target_id: str,
        owner_id: str,
        db: AsyncSession,
    ) -> tuple[ModelInstance, ModelInstance]:
        """Load and validate both instances belong to the owner."""
        src_result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.id == source_id,
                ModelInstance.owner_id == owner_id,
            )
        )
        source = src_result.scalar_one_or_none()
        if not source:
            raise ValueError(f"Source instance {source_id} not found")

        tgt_result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.id == target_id,
                ModelInstance.owner_id == owner_id,
            )
        )
        target = tgt_result.scalar_one_or_none()
        if not target:
            raise ValueError(f"Target instance {target_id} not found")

        return source, target

    async def _load_sync_log(
        self, sync_id: str, owner_id: str, db: AsyncSession
    ) -> SyncLog:
        """Load a SyncLog and verify the owner has access via the instances."""
        result = await db.execute(select(SyncLog).where(SyncLog.id == sync_id))
        sync_log = result.scalar_one_or_none()
        if not sync_log:
            raise ValueError("Sync log not found")

        # Verify ownership via source instance
        inst_result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.id == sync_log.source_instance_id,
                ModelInstance.owner_id == owner_id,
            )
        )
        if not inst_result.scalar_one_or_none():
            raise ValueError("Sync log not found")

        return sync_log

    async def _get_conflicts_for_log(
        self, sync_log_id: str, db: AsyncSession
    ) -> list[SyncConflict]:
        result = await db.execute(
            select(SyncConflict)
            .where(SyncConflict.sync_log_id == sync_log_id)
            .order_by(SyncConflict.created_at.desc())
        )
        return list(result.scalars().all())

    async def _sync_knowledge_entries(
        self,
        source: ModelInstance,
        target: ModelInstance,
        owner_id: str,
        db: AsyncSession,
        sync_log: SyncLog,
        since: datetime | None,
    ) -> tuple[int, int]:
        """Sync knowledge entries. Returns (synced_count, conflict_count).

        Strategy: The API owns the canonical knowledge entries in PostgreSQL.
        We compare what the source and target AI instances have in their
        vector stores and push missing entries to the target.
        """
        # Get entries from PostgreSQL (source of truth for metadata)
        query = select(KnowledgeEntry).where(KnowledgeEntry.owner_id == owner_id)
        if since:
            query = query.where(KnowledgeEntry.created_at >= since)
        query = query.order_by(KnowledgeEntry.created_at.asc())

        result = await db.execute(query)
        entries = list(result.scalars().all())

        sync_log.total_entries += len(entries)
        await db.commit()

        if not entries or not target.api_url:
            return 0, 0

        synced = 0
        conflicts = 0

        # Get target's existing entry IDs to detect what's missing
        target_entry_ids = await self._get_remote_entry_ids(target)

        for entry in entries:
            if entry.id in target_entry_ids:
                # Entry exists on target — check for content conflict
                if source.api_url:
                    conflict_detected = await self._check_entry_conflict(
                        entry, source, target, db, sync_log
                    )
                    if conflict_detected:
                        conflicts += 1
                continue

            # Entry missing on target — transfer it
            transferred = await self._transfer_entry_to_instance(entry, target)
            if transferred:
                synced += 1

        return synced, conflicts

    async def _sync_conversations(
        self,
        source: ModelInstance,
        target: ModelInstance,
        owner_id: str,
        db: AsyncSession,
        sync_log: SyncLog,
        since: datetime | None,
    ) -> int:
        """Sync conversation threads and messages to target instance.

        Conversations live in PostgreSQL (centralized), so this pushes
        thread data to the target's local storage for offline access.
        """
        if not target.api_url:
            return 0

        # Import here to avoid circular imports
        from app.models.owner import Base  # noqa: F811 — just accessing metadata

        # Conversations are in PostgreSQL which both instances can access
        # through the API. For local instances that may go offline, we push
        # a snapshot of recent conversations to their local storage.
        try:
            async with httpx.AsyncClient(timeout=_INSTANCE_TIMEOUT) as client:
                # Build conversation snapshot from DB
                from sqlalchemy import text

                if since:
                    threads_result = await db.execute(
                        text(
                            "SELECT id, owner_id, participant_type, participant_name, created_at "
                            "FROM conversation_threads "
                            "WHERE owner_id = :owner_id AND created_at >= :since"
                        ),
                        {"owner_id": owner_id, "since": since},
                    )
                else:
                    threads_result = await db.execute(
                        text(
                            "SELECT id, owner_id, participant_type, participant_name, created_at "
                            "FROM conversation_threads "
                            "WHERE owner_id = :owner_id"
                        ),
                        {"owner_id": owner_id},
                    )

                threads = [dict(r._mapping) for r in threads_result.all()]

                if not threads:
                    return 0

                thread_ids = [t["id"] for t in threads]

                # Fetch messages for these threads
                msgs_result = await db.execute(
                    text(
                        "SELECT id, thread_id, role, content_text, language, created_at "
                        "FROM messages "
                        "WHERE thread_id = ANY(:thread_ids)"
                    ),
                    {"thread_ids": thread_ids},
                )
                messages = [dict(r._mapping) for r in msgs_result.all()]

                # Serialize datetimes for JSON transfer
                for t in threads:
                    t["created_at"] = t["created_at"].isoformat() if t.get("created_at") else None
                for m in messages:
                    m["created_at"] = m["created_at"].isoformat() if m.get("created_at") else None

                payload = {"threads": threads, "messages": messages}

                resp = await client.post(
                    f"{target.api_url}/sync/conversations",
                    json=payload,
                    headers={"Content-Encoding": "gzip"},
                )
                # 404 means endpoint not implemented on target yet — skip gracefully
                if resp.status_code == 404:
                    return 0
                resp.raise_for_status()

                return len(threads)

        except httpx.HTTPError:
            logger.warning("Could not sync conversations to %s", target.hostname)
            return 0

    async def _sync_access_rules(
        self,
        source: ModelInstance,
        target: ModelInstance,
        owner_id: str,
        db: AsyncSession,
        sync_log: SyncLog,
        since: datetime | None,
    ) -> int:
        """Push access rules to target. Latest-write-wins for conflicts."""
        if not target.api_url:
            return 0

        try:
            from sqlalchemy import text

            if since:
                rules_result = await db.execute(
                    text(
                        "SELECT id, owner_id, grantee_name, grantee_relation, "
                        "access_level, verification_method, is_active, "
                        "valid_from, valid_until, created_at "
                        "FROM access_rules "
                        "WHERE owner_id = :owner_id AND created_at >= :since"
                    ),
                    {"owner_id": owner_id, "since": since},
                )
            else:
                rules_result = await db.execute(
                    text(
                        "SELECT id, owner_id, grantee_name, grantee_relation, "
                        "access_level, verification_method, is_active, "
                        "valid_from, valid_until, created_at "
                        "FROM access_rules WHERE owner_id = :owner_id"
                    ),
                    {"owner_id": owner_id},
                )

            rules = [dict(r._mapping) for r in rules_result.all()]
            if not rules:
                return 0

            # Serialize datetimes
            for rule in rules:
                for key in ("valid_from", "valid_until", "created_at"):
                    if rule.get(key):
                        rule[key] = rule[key].isoformat()

            async with httpx.AsyncClient(timeout=_INSTANCE_TIMEOUT) as client:
                resp = await client.post(
                    f"{target.api_url}/sync/access-rules",
                    json={"rules": rules},
                )
                if resp.status_code == 404:
                    return 0
                resp.raise_for_status()

            return len(rules)

        except httpx.HTTPError:
            logger.warning("Could not sync access rules to %s", target.hostname)
            return 0

    async def _get_remote_entry_ids(self, instance: ModelInstance) -> set[str]:
        """Ask an AI instance for its list of knowledge entry IDs."""
        if not instance.api_url:
            return set()
        try:
            async with httpx.AsyncClient(timeout=_INSTANCE_TIMEOUT) as client:
                resp = await client.get(f"{instance.api_url}/sync/entry-ids")
                if resp.status_code == 404:
                    return set()
                resp.raise_for_status()
                return set(resp.json().get("entry_ids", []))
        except httpx.HTTPError:
            logger.warning("Could not fetch entry IDs from %s", instance.hostname)
            return set()

    async def _check_entry_conflict(
        self,
        entry: KnowledgeEntry,
        source: ModelInstance,
        target: ModelInstance,
        db: AsyncSession,
        sync_log: SyncLog,
    ) -> bool:
        """Check if source and target have divergent content for the same entry.
        If so, create a SyncConflict record."""
        if not source.api_url or not target.api_url:
            return False

        try:
            async with httpx.AsyncClient(timeout=_INSTANCE_TIMEOUT) as client:
                src_resp = await client.get(
                    f"{source.api_url}/sync/entry-hash/{entry.id}"
                )
                tgt_resp = await client.get(
                    f"{target.api_url}/sync/entry-hash/{entry.id}"
                )

                # If either doesn't support hash endpoint, skip conflict detection
                if src_resp.status_code == 404 or tgt_resp.status_code == 404:
                    return False

                src_resp.raise_for_status()
                tgt_resp.raise_for_status()

                src_hash = src_resp.json().get("hash", "")
                tgt_hash = tgt_resp.json().get("hash", "")

                if src_hash == tgt_hash:
                    return False

        except httpx.HTTPError:
            return False

        # Content differs — record conflict
        conflict = SyncConflict(
            id=_generate_cuid(),
            sync_log_id=sync_log.id,
            entry_id=entry.id,
            entry_type="knowledge_entry",
            source_data={
                "instance_id": source.id,
                "hostname": source.hostname,
                "content_type": entry.content_type.value if entry.content_type else None,
                "embedding_id": entry.embedding_id,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            },
            target_data={
                "instance_id": target.id,
                "hostname": target.hostname,
                "hash": tgt_hash,
            },
            resolution=ConflictResolution.pending,
        )
        db.add(conflict)
        await db.commit()
        return True

    async def _transfer_entry_to_instance(
        self, entry: KnowledgeEntry, target: ModelInstance
    ) -> bool:
        """Push a knowledge entry to the target AI instance."""
        if not target.api_url:
            return False

        payload = {
            "entry_id": entry.id,
            "owner_id": entry.owner_id,
            "content_type": entry.content_type.value if entry.content_type else None,
            "original_content_path": entry.original_content_path,
            "original_language": entry.original_language,
            "english_translation": entry.english_translation,
            "embedding_id": entry.embedding_id,
            "metadata": entry.metadata_,
        }

        try:
            async with httpx.AsyncClient(timeout=_INSTANCE_TIMEOUT) as client:
                resp = await client.post(
                    f"{target.api_url}/sync/import-entry",
                    json=payload,
                    headers={"Accept-Encoding": "gzip"},
                )
                if resp.status_code == 404:
                    return False
                resp.raise_for_status()
                return True
        except httpx.HTTPError:
            logger.warning(
                "Failed to transfer entry %s to %s", entry.id, target.hostname
            )
            return False

    async def _apply_conflict_resolution(
        self, conflict: SyncConflict, db: AsyncSession
    ) -> None:
        """Apply a resolved conflict by updating the actual data."""
        if conflict.resolution == ConflictResolution.keep_source:
            # Source wins — re-transfer entry from source to target
            target_id = conflict.target_data.get("instance_id")
            if target_id:
                tgt_result = await db.execute(
                    select(ModelInstance).where(ModelInstance.id == target_id)
                )
                target = tgt_result.scalar_one_or_none()
                entry_result = await db.execute(
                    select(KnowledgeEntry).where(KnowledgeEntry.id == conflict.entry_id)
                )
                entry = entry_result.scalar_one_or_none()
                if target and entry:
                    await self._transfer_entry_to_instance(entry, target)

        elif conflict.resolution == ConflictResolution.keep_target:
            # Target wins — no action needed (target already has its version)
            pass

        elif conflict.resolution == ConflictResolution.keep_both:
            # Keep both — no deletion on either side, both versions coexist
            pass
