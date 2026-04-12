from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import embeddings, generation, health, knowledge, models, rag, vectors

app = FastAPI(
    title="Replica AI Service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(models.router, tags=["models"])
app.include_router(generation.router, tags=["generation"])
app.include_router(embeddings.router, tags=["embeddings"])
app.include_router(vectors.router, tags=["vectors"])
app.include_router(knowledge.router, tags=["knowledge"])
app.include_router(rag.router, tags=["rag"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Replica AI Service"}
