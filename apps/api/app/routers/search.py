from fastapi import APIRouter, Depends

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_auth
from app.models.search import SearchRequest, SearchResponse, SearchResultItem

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_knowledge(
    body: SearchRequest,
    auth: AuthContext = Depends(require_auth),
    ai: AIServiceClient = Depends(get_ai_client),
) -> SearchResponse:
    result = await ai.vector_search(
        owner_id=auth.subject_id,
        query=body.query,
        top_k=body.top_k,
        content_type=body.content_type.value if body.content_type else None,
    )

    items = [SearchResultItem(**r) for r in result.get("results", [])]

    return SearchResponse(
        query=body.query,
        results=items,
        total=len(items),
    )
