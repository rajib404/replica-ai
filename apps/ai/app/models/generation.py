from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str
    model: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048


class StreamRequest(BaseModel):
    prompt: str
    model: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048


class GenerateResponse(BaseModel):
    response: str
    model: str | None = None
    done: bool = True


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    max_tokens: int = 512


class SummarizeResponse(BaseModel):
    summary: str
