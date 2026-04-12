import json

from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.models.generation import (
    GenerateRequest,
    GenerateResponse,
    StreamRequest,
    SummarizeRequest,
    SummarizeResponse,
)
from app.services.llm_engine import OllamaClient

router = APIRouter()

_ollama = OllamaClient()

SUMMARIZE_PROMPT = """\
Summarize the following conversation into a concise paragraph (3-5 sentences) \
that captures the key topics, facts shared, and any decisions made. \
Preserve important personal details.

Conversation:
{text}"""


@router.post("/generate", response_model=GenerateResponse)
async def generate(body: GenerateRequest) -> GenerateResponse:
    """Non-streaming text generation."""
    try:
        result = await _ollama.generate_response(
            prompt=body.prompt,
            model=body.model,
            system_prompt=body.system_prompt,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
        return GenerateResponse(
            response=result.get("response", ""),
            model=result.get("model"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Generation failed: {e}",
        ) from e


@router.post("/generate/stream")
async def generate_stream(body: StreamRequest) -> EventSourceResponse:
    """Streaming generation, returns SSE."""

    async def event_generator():
        try:
            async for chunk in _ollama.generate_response_stream(
                prompt=body.prompt,
                model=body.model,
                system_prompt=body.system_prompt,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            ):
                token = chunk.get("response", "")
                if token:
                    yield {"event": "token", "data": json.dumps({"token": token})}
                if chunk.get("done"):
                    yield {"event": "done", "data": json.dumps({"done": True})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_generator())


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(body: SummarizeRequest) -> SummarizeResponse:
    """Summarize conversation text."""
    prompt = SUMMARIZE_PROMPT.format(text=body.text)
    try:
        result = await _ollama.generate_response(
            prompt=prompt,
            temperature=0.3,
            max_tokens=body.max_tokens,
        )
        return SummarizeResponse(summary=result.get("response", ""))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Summarization failed: {e}",
        ) from e
