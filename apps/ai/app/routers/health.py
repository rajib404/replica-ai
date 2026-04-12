from fastapi import APIRouter

from app.core.qdrant import get_qdrant
from app.services.llm_engine import OllamaClient

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check — reports Ollama + Qdrant reachability."""
    ollama = OllamaClient()
    qdrant = get_qdrant()

    ollama_health = await ollama.health_check()
    qdrant_ok = await qdrant.health_check()

    overall = "ok" if ollama_health["status"] == "ok" and qdrant_ok else "degraded"

    return {
        "status": overall,
        "ollama": ollama_health,
        "qdrant": {"status": "ok" if qdrant_ok else "unreachable"},
    }
