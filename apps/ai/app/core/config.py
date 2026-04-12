from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Replica AI Service"
    debug: bool = False

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "mistral:7b-instruct"
    ollama_request_timeout: float = 300.0  # 5 min for slow generations

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "knowledge"

    # Redis (shared with main API for task tracking)
    redis_url: str = "redis://localhost:6379/0"

    # File storage
    storage_base_path: str = "./storage"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
