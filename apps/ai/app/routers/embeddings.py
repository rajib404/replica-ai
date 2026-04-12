from fastapi import APIRouter, HTTPException, status

from app.models.embeddings import EmbeddingRequest, EmbeddingResponse
from app.services.llm_engine import OllamaClient

router = APIRouter()

_ollama = OllamaClient()


@router.post("/embeddings", response_model=EmbeddingResponse)
async def generate_embedding(body: EmbeddingRequest) -> EmbeddingResponse:
    """Generate embedding vector for text."""
    try:
        vector = await _ollama.generate_embedding(body.text, model=body.model)
        return EmbeddingResponse(embedding=vector, dimensions=len(vector))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding generation failed: {e}",
        ) from e
