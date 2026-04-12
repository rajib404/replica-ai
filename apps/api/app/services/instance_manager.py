import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_secret
from app.models.instance import InstanceResponse
from app.models.owner import InstanceStatus, ModelInstance

logger = logging.getLogger(__name__)


def _generate_cuid() -> str:
    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _instance_to_response(inst: ModelInstance) -> InstanceResponse:
    return InstanceResponse(
        id=inst.id,
        owner_id=inst.owner_id,
        instance_type=inst.instance_type.value,
        hostname=inst.hostname,
        status=inst.status.value,
        version=inst.version,
        capabilities=inst.capabilities,
        is_primary=inst.is_primary,
        last_heartbeat_at=inst.last_heartbeat_at,
        api_url=inst.api_url,
        created_at=inst.created_at,
    )


class InstanceRegistry:
    """Manages registration, discovery, and health of model instances."""

    async def register_instance(
        self,
        owner_id: str,
        instance_type: str,
        hostname: str,
        db: AsyncSession,
        api_url: str | None = None,
        capabilities: list[str] | None = None,
    ) -> dict:
        instance_id = _generate_cuid()
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_secret(raw_token)

        instance = ModelInstance(
            id=instance_id,
            owner_id=owner_id,
            instance_type=instance_type,
            hostname=hostname,
            api_url=api_url,
            capabilities=capabilities or ["generate", "embed", "ingest"],
            is_primary=False,
            status=InstanceStatus.active,
            auth_token_hash=token_hash,
            last_heartbeat_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        jwt_token = create_access_token(
            subject=owner_id,
            role="instance",
            extra={"instance_id": instance_id},
        )

        return {
            "instance": _instance_to_response(instance),
            "auth_token": jwt_token,
        }

    async def discover_instances(
        self,
        owner_id: str,
        db: AsyncSession,
    ) -> list[InstanceResponse]:
        result = await db.execute(
            select(ModelInstance).where(ModelInstance.owner_id == owner_id)
        )
        instances = list(result.scalars().all())

        responses: list[InstanceResponse] = []
        for inst in instances:
            if inst.api_url and inst.status != InstanceStatus.offline:
                try:
                    async with httpx.AsyncClient(timeout=3) as client:
                        resp = await client.get(f"{inst.api_url}/health")
                        if resp.status_code != 200:
                            inst.status = InstanceStatus.offline
                            await db.commit()
                except Exception:
                    inst.status = InstanceStatus.offline
                    await db.commit()

            responses.append(_instance_to_response(inst))

        return responses

    async def promote_to_primary(
        self,
        instance_id: str,
        owner_id: str,
        db: AsyncSession,
    ) -> InstanceResponse:
        result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.id == instance_id,
                ModelInstance.owner_id == owner_id,
            )
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("Instance not found or not owned by this owner")

        # Demote all other instances for this owner
        await db.execute(
            update(ModelInstance)
            .where(ModelInstance.owner_id == owner_id)
            .values(is_primary=False)
        )

        instance.is_primary = True
        await db.commit()
        await db.refresh(instance)
        return _instance_to_response(instance)

    async def record_heartbeat(
        self,
        instance_id: str,
        owner_id: str,
        db: AsyncSession,
    ) -> InstanceResponse:
        result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.id == instance_id,
                ModelInstance.owner_id == owner_id,
            )
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("Instance not found or not owned by this owner")

        instance.last_heartbeat_at = datetime.now(UTC).replace(tzinfo=None)
        instance.status = InstanceStatus.active
        await db.commit()
        await db.refresh(instance)
        return _instance_to_response(instance)

    async def deregister_instance(
        self,
        instance_id: str,
        owner_id: str,
        db: AsyncSession,
    ) -> None:
        result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.id == instance_id,
                ModelInstance.owner_id == owner_id,
            )
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("Instance not found or not owned by this owner")

        await db.delete(instance)
        await db.commit()

    @staticmethod
    async def check_stale_instances(db: AsyncSession) -> int:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            seconds=settings.instance_heartbeat_timeout_seconds
        )
        result = await db.execute(
            select(ModelInstance).where(
                ModelInstance.status != InstanceStatus.offline,
                ModelInstance.last_heartbeat_at < cutoff,
            )
        )
        stale = list(result.scalars().all())

        for inst in stale:
            inst.status = InstanceStatus.offline

        if stale:
            await db.commit()
            logger.info("Marked %d stale instance(s) as offline", len(stale))

        return len(stale)
