"""Async HTTP client for the standalone AI service (apps/ai).

All non-streaming calls are wrapped in :func:`app.core.retry.ollama_retry`,
which retries transient network errors and raises
:class:`app.core.exceptions.ModelUnavailableError` on final failure.
Streaming calls (``generate_stream``, ``rag_stream``) can't be retried
mid-stream, so they surface the underlying ``httpx`` error and the caller
is responsible for handling it (chat router catches and sends a
``WSError`` frame to the client).
"""

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings
from app.core.exceptions import ModelUnavailableError, UpstreamError
from app.core.retry import ollama_retry

logger = logging.getLogger(__name__)


class AIServiceClient:
    """Thin async wrapper that calls the AI service endpoints."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.ai_service_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -- Health --

    async def health(self) -> dict:
        """Fetch the AI service health snapshot.

        Not retried — callers should tolerate failure and report a
        'degraded' status to the user. Returns a dict with at least a
        ``status`` key, or raises the underlying httpx error.
        """
        client = await self._get_client()
        resp = await client.get("/health")
        resp.raise_for_status()
        return resp.json()

    async def health_safe(self) -> dict:
        """Non-raising variant of ``health()`` — returns a structured
        error dict instead of throwing. Used by the health dashboard.
        """
        try:
            return await self.health()
        except httpx.ConnectError:
            return {"status": "unreachable", "error": "Cannot connect to AI service"}
        except httpx.TimeoutException:
            return {"status": "timeout", "error": "AI service did not respond in time"}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "error": str(e)}

    # -- Models --

    @ollama_retry
    async def list_models(self) -> dict:
        client = await self._get_client()
        resp = await client.get("/models")
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def pull_model(self, model: str) -> dict:
        client = await self._get_client()
        resp = await client.post("/models/pull", json={"model": model})
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def create_model(
        self,
        owner_id: str,
        owner_name: str,
        language: str,
        additions: str = "",
        base_model: str | None = None,
    ) -> dict:
        client = await self._get_client()
        payload: dict = {
            "owner_id": owner_id,
            "owner_name": owner_name,
            "language": language,
            "additions": additions,
        }
        if base_model:
            payload["base_model"] = base_model
        resp = await client.post("/models/create", json=payload)
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def get_model(self, name: str) -> dict:
        client = await self._get_client()
        resp = await client.get(f"/models/{name}")
        resp.raise_for_status()
        return resp.json()

    # -- Generation --

    @ollama_retry
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/generate",
            json={
                "prompt": prompt,
                "model": model,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[dict, None]:
        """Stream generation tokens from AI service SSE endpoint."""
        client = await self._get_client()
        async with client.stream(
            "POST",
            "/generate/stream",
            json={
                "prompt": prompt,
                "model": model,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=None,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue

    @ollama_retry
    async def summarize(self, text: str, max_tokens: int = 512) -> str:
        client = await self._get_client()
        resp = await client.post(
            "/summarize",
            json={"text": text, "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        return resp.json().get("summary", "")

    # -- Embeddings --

    @ollama_retry
    async def embed(self, text: str, model: str | None = None) -> list[float]:
        client = await self._get_client()
        resp = await client.post(
            "/embeddings",
            json={"text": text, "model": model},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    # -- Vectors --

    @ollama_retry
    async def vector_search(
        self,
        owner_id: str,
        query: str,
        top_k: int = 5,
        content_type: str | None = None,
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/vectors/search",
            json={
                "owner_id": owner_id,
                "query": query,
                "top_k": top_k,
                "content_type": content_type,
            },
        )
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def delete_vectors(self, entry_id: str) -> None:
        client = await self._get_client()
        resp = await client.delete(f"/vectors/{entry_id}")
        resp.raise_for_status()

    # -- Knowledge ingestion --

    @ollama_retry
    async def ingest_text(
        self,
        owner_id: str,
        text: str,
        language: str | None = None,
        english_translation: str | None = None,
    ) -> dict:
        client = await self._get_client()
        payload: dict = {"owner_id": owner_id, "text": text, "language": language}
        if english_translation:
            payload["english_translation"] = english_translation
        resp = await client.post("/ingest/text", json=payload)
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def ingest_audio(
        self, owner_id: str, file_bytes: bytes, filename: str
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/ingest/audio",
            params={"owner_id": owner_id},
            files={"file": (filename, file_bytes)},
        )
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def ingest_video(
        self, owner_id: str, file_bytes: bytes, filename: str
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/ingest/video",
            params={"owner_id": owner_id},
            files={"file": (filename, file_bytes)},
        )
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def ingest_document(
        self, owner_id: str, file_bytes: bytes, filename: str
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/ingest/document",
            params={"owner_id": owner_id},
            files={"file": (filename, file_bytes)},
        )
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def transcribe(self, file_bytes: bytes, filename: str) -> dict:
        """Synchronously transcribe audio. Returns {text, language}."""
        client = await self._get_client()
        resp = await client.post(
            "/transcribe",
            files={"file": (filename, file_bytes)},
        )
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def ingest_image(
        self, owner_id: str, file_bytes: bytes, filename: str
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/ingest/image",
            params={"owner_id": owner_id},
            files={"file": (filename, file_bytes)},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_file_bytes(self, relative_path: str) -> tuple[bytes, str]:
        """Fetch a stored file from the AI service. Returns (bytes, mime_type)."""
        client = await self._get_client()
        resp = await client.get(f"/storage/{relative_path}")
        resp.raise_for_status()
        mime = resp.headers.get("content-type", "application/octet-stream")
        return resp.content, mime

    async def get_task_status(self, task_id: str) -> dict:
        client = await self._get_client()
        resp = await client.get(f"/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json()

    # -- RAG --

    @ollama_retry
    async def rag_search(
        self,
        owner_id: str,
        query: str,
        top_k: int = 5,
        content_type: str | None = None,
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/rag/search",
            json={
                "owner_id": owner_id,
                "query": query,
                "top_k": top_k,
                "content_type": content_type,
            },
        )
        resp.raise_for_status()
        return resp.json()

    @ollama_retry
    async def rag_generate(
        self,
        owner_id: str,
        message: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> dict:
        client = await self._get_client()
        resp = await client.post(
            "/rag/generate",
            json={
                "owner_id": owner_id,
                "message": message,
                "conversation_history": conversation_history,
                "system_prompt": system_prompt,
                "model": model,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def rag_stream(
        self,
        owner_id: str,
        message: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream RAG response tokens from AI service SSE endpoint."""
        client = await self._get_client()
        async with client.stream(
            "POST",
            "/rag/stream",
            json={
                "owner_id": owner_id,
                "message": message,
                "conversation_history": conversation_history,
                "system_prompt": system_prompt,
                "model": model,
            },
            timeout=None,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue


_ai_client: AIServiceClient | None = None


def get_ai_client() -> AIServiceClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIServiceClient()
    return _ai_client


def translate_ai_error(exc: BaseException) -> BaseException:
    """Map an ``httpx`` error raised by the AI client into a domain exception.

    Useful for streaming entry points that can't be wrapped with ``@ollama_retry``.
    Unrecognised errors are returned unchanged so the caller can re-raise.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        return ModelUnavailableError(
            "The AI model is temporarily unreachable. Please try again in a minute.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if 500 <= status_code < 600:
            return ModelUnavailableError(
                "The AI model returned an internal error. Please try again.",
                details={"status": status_code},
            )
        return UpstreamError(
            f"AI service returned HTTP {status_code}.",
            details={"status": status_code},
        )
    return exc
