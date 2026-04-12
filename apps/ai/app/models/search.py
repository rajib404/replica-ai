from pydantic import BaseModel, Field


class VectorSearchRequest(BaseModel):
    owner_id: str
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    content_type: str | None = None


class SearchResultItem(BaseModel):
    entry_id: str
    content_type: str
    score: float
    content_preview: str | None = None
    original_language: str | None = None
    chunk_index: int = 0


class VectorSearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class RAGSearchRequest(BaseModel):
    owner_id: str
    message: str = Field(..., min_length=1)
    conversation_history: list[dict[str, str]] = []
    system_prompt: str | None = None
    model: str | None = None


class RAGSearchResponse(BaseModel):
    """Non-streaming RAG response."""
    response: str
    sources: list[dict]
    query_used: str


class RAGStreamRequest(BaseModel):
    owner_id: str
    message: str = Field(..., min_length=1)
    conversation_history: list[dict[str, str]] = []
    system_prompt: str | None = None
    model: str | None = None
