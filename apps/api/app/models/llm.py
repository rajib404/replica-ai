from pydantic import BaseModel, Field


class ModelStatusResponse(BaseModel):
    ollama_status: str
    ollama_detail: str | None = None
    models: list[dict] = []


class ModelInitializeRequest(BaseModel):
    owner_id: str
    model: str | None = Field(
        default=None,
        description="Override the default base model (e.g. 'llama3:8b')",
    )


class ModelInitializeResponse(BaseModel):
    base_model_status: str
    owner_model: dict


class ModelInfoResponse(BaseModel):
    model_name: str | None = None
    exists: bool = False
    details: dict | None = None


class ModelSwitchRequest(BaseModel):
    new_base_model: str = Field(
        ...,
        description="The new base model to switch to (e.g. 'qwen2.5:3b')",
    )


class ModelSwitchResponse(BaseModel):
    status: str = Field(description="'switching', 'no_change', or 'error'")
    previous_base_model: str | None = None
    new_base_model: str | None = None
    model_pull_started: bool = False
    retrain_triggered: bool = False
    message: str = ""
