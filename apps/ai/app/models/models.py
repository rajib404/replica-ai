from pydantic import BaseModel


class ModelPullRequest(BaseModel):
    model: str


class ModelCreateRequest(BaseModel):
    owner_id: str
    owner_name: str
    language: str = "en"
    additions: str = ""
    base_model: str | None = None


class ModelStatus(BaseModel):
    ollama_status: str
    ollama_detail: str | None = None
    models: list[dict] = []


class ModelInfoResponse(BaseModel):
    model_name: str | None = None
    exists: bool = False
    details: dict | None = None


class ModelCreateResponse(BaseModel):
    model_name: str
    owner_id: str
    system_prompt: str
    progress: list[dict] = []
