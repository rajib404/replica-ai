import logging
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Async wrapper around the Qdrant vector database."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._host = host or settings.qdrant_host
        self._port = port or settings.qdrant_port
        self._client: AsyncQdrantClient | None = None
        self._collection_ready = False
        self._indexes_ready = False

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(host=self._host, port=self._port)
        return self._client

    async def ensure_collection(self, vector_size: int) -> None:
        """Create the knowledge collection if it doesn't exist."""
        if self._collection_ready:
            return

        client = await self._get_client()
        collection_name = settings.qdrant_collection_name
        collections = await client.get_collections()
        existing = [c.name for c in collections.collections]

        if collection_name not in existing:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s' (dim=%d)", collection_name, vector_size)

        self._collection_ready = True

    async def ensure_payload_indexes(self) -> None:
        """Create payload indexes on owner_id and content_type for fast filtering."""
        if self._indexes_ready:
            return

        client = await self._get_client()
        collection_name = settings.qdrant_collection_name

        for field in ("owner_id", "content_type"):
            try:
                await client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.info("Created payload index on '%s'", field)
            except Exception:
                # Index may already exist — Qdrant returns an error in that case
                pass

        self._indexes_ready = True

    async def upsert_embedding(
        self,
        entry_id: str,
        vector: list[float],
        owner_id: str,
        content_type: str,
        language: str,
        chunk_index: int = 0,
        content_preview: str | None = None,
    ) -> str:
        """Upsert a single embedding point. Returns the point UUID."""
        client = await self._get_client()
        point_id = str(uuid.uuid4())

        payload: dict = {
            "entry_id": entry_id,
            "owner_id": owner_id,
            "content_type": content_type,
            "language": language,
            "chunk_index": chunk_index,
        }
        if content_preview is not None:
            payload["content_preview"] = content_preview

        await client.upsert(
            collection_name=settings.qdrant_collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )
        return point_id

    async def delete_by_entry_id(self, entry_id: str) -> None:
        """Delete all points belonging to a knowledge entry."""
        client = await self._get_client()
        await client.delete(
            collection_name=settings.qdrant_collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="entry_id", match=MatchValue(value=entry_id))]
            ),
        )

    async def search(
        self,
        query_vector: list[float],
        owner_id: str,
        limit: int = 10,
        content_type: str | None = None,
    ) -> list[dict]:
        """Filtered nearest-neighbor search scoped to an owner."""
        client = await self._get_client()

        must_conditions = [
            FieldCondition(key="owner_id", match=MatchValue(value=owner_id))
        ]
        if content_type is not None:
            must_conditions.append(
                FieldCondition(key="content_type", match=MatchValue(value=content_type))
            )

        results = await client.query_points(
            collection_name=settings.qdrant_collection_name,
            query=query_vector,
            query_filter=Filter(must=must_conditions),
            limit=limit,
        )
        return [
            {"id": str(r.id), "score": r.score, "payload": r.payload}
            for r in results.points
        ]

    async def health_check(self) -> bool:
        """Return True if Qdrant is reachable."""
        try:
            client = await self._get_client()
            await client.get_collections()
            return True
        except Exception:
            return False


_qdrant_service: QdrantService | None = None


def get_qdrant() -> QdrantService:
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
