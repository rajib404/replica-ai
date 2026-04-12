from fastapi import APIRouter, HTTPException, status

from app.models.search import SearchResultItem, VectorSearchRequest, VectorSearchResponse
from app.services.knowledge import KnowledgeIngestor
from app.services.search import KnowledgeSearch

router = APIRouter()

_searcher = KnowledgeSearch()
_ingestor = KnowledgeIngestor()


@router.post("/vectors/search", response_model=VectorSearchResponse)
async def vector_search(body: VectorSearchRequest) -> VectorSearchResponse:
    """Search Qdrant by owner_id + query text (embeds internally)."""
    results = await _searcher.search(
        owner_id=body.owner_id,
        query=body.query,
        top_k=body.top_k,
        content_type_filter=body.content_type,
    )

    items = [
        SearchResultItem(
            entry_id=r.entry_id,
            content_type=r.content_type,
            score=r.score,
            content_preview=r.content_preview,
            original_language=r.original_language,
            chunk_index=r.chunk_index,
        )
        for r in results
    ]

    return VectorSearchResponse(
        query=body.query,
        results=items,
        total=len(items),
    )


@router.delete("/vectors/{entry_id}", status_code=204)
async def delete_vectors(entry_id: str) -> None:
    """Delete all vectors for a knowledge entry."""
    try:
        await _ingestor.delete_vectors(entry_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete vectors: {e}",
        ) from e
