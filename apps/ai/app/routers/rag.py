import json

from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.models.search import (
    RAGSearchRequest,
    RAGSearchResponse,
    RAGStreamRequest,
    SearchResultItem,
    VectorSearchRequest,
    VectorSearchResponse,
)
from app.services.search import RAGEngine

router = APIRouter()

_rag = RAGEngine()


@router.post("/rag/search", response_model=VectorSearchResponse)
async def rag_search(body: VectorSearchRequest) -> VectorSearchResponse:
    """Extract queries from message, search Qdrant, return ranked results with content previews."""
    results = await _rag.searcher.search(
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


@router.post("/rag/generate", response_model=RAGSearchResponse)
async def rag_generate(body: RAGSearchRequest) -> RAGSearchResponse:
    """Full RAG: search + generate non-streaming response."""
    try:
        result = await _rag.generate_grounded_response(
            owner_id=body.owner_id,
            user_message=body.message,
            conversation_history=body.conversation_history,
            system_prompt=body.system_prompt,
            model=body.model,
        )
        return RAGSearchResponse(
            response=result["response"],
            sources=result["sources"],
            query_used=result["query_used"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAG generation failed: {e}",
        ) from e


@router.post("/rag/stream")
async def rag_stream(body: RAGStreamRequest) -> EventSourceResponse:
    """Full RAG: search + stream response via SSE."""

    async def event_generator():
        try:
            async for event in _rag.generate_grounded_response_stream(
                owner_id=body.owner_id,
                user_message=body.message,
                conversation_history=body.conversation_history,
                system_prompt=body.system_prompt,
                model=body.model,
            ):
                event_type = event.get("type", "token")
                yield {"event": event_type, "data": json.dumps(event)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_generator())
