from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Replica AI Service"
    debug: bool = False

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "mistral:7b-instruct"
    # Chat models (llama3.2, mistral, etc.) don't support the embeddings
    # capability — a dedicated embedding model is required for RAG.
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_request_timeout: float = 300.0  # 5 min for slow generations

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "knowledge"

    # Redis (shared with main API for task tracking)
    redis_url: str = "redis://localhost:6379/0"

    # File storage
    storage_base_path: str = "./storage"

    # faster-whisper model cache. Relative so it resolves under the
    # container's /app WORKDIR in prod (matching the ai_model_cache volume
    # mount) and under apps/ai/ in local dev.
    whisper_model_cache_dir: str = "./model_cache"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
