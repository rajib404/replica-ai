from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    model: str | None = None


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    dimensions: int
