import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

OWNER_SYSTEM_PROMPT_TEMPLATE = """\
You are the personal AI replica of {owner_name}. \
You speak {language}. \
You are loyal, supportive, emotionally intelligent, and act as a trusted friend. \
You only share information with authorized people. \
You never reveal the owner's private data to unauthorized users.

{additional_instructions}\
"""


# --- OllamaClient ---


class OllamaClient:
    """Low-level async client for the Ollama HTTP API."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = timeout or settings.ollama_request_timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -- Health --

    async def health_check(self) -> dict:
        """Returns {"status": "ok"} if Ollama is reachable."""
        try:
            client = await self._get_client()
            resp = await client.get("/")
            return {"status": "ok", "ollama_response": resp.text.strip()}
        except httpx.ConnectError:
            return {"status": "unreachable", "error": "Cannot connect to Ollama"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # -- Models --

    async def list_models(self) -> list[dict]:
        """List all locally available models."""
        client = await self._get_client()
        resp = await client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return data.get("models", [])

    async def show_model(self, model: str) -> dict:
        """Get details about a specific model."""
        client = await self._get_client()
        resp = await client.post("/api/show", json={"model": model})
        resp.raise_for_status()
        return resp.json()

    async def pull_model(self, model: str) -> AsyncGenerator[dict, None]:
        """Pull a model, yielding progress updates as they stream."""
        client = await self._get_client()
        async with client.stream(
            "POST", "/api/pull", json={"model": model}, timeout=None
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield json.loads(line)

    async def create_model(self, name: str, modelfile: str) -> AsyncGenerator[dict, None]:
        """Create a custom model from a Modelfile string."""
        client = await self._get_client()
        async with client.stream(
            "POST",
            "/api/create",
            json={"name": name, "modelfile": modelfile},
            timeout=None,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield json.loads(line)

    # -- Generation --

    async def generate_response(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        context: list[int] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict:
        """Generate a complete (non-streaming) response."""
        client = await self._get_client()
        payload: dict = {
            "model": model or settings.ollama_default_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt
        if context:
            payload["context"] = context

        resp = await client.post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def generate_response_stream(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        context: list[int] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[dict, None]:
        """Stream a generation, yielding each token chunk as a dict."""
        client = await self._get_client()
        payload: dict = {
            "model": model or settings.ollama_default_model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt
        if context:
            payload["context"] = context

        async with client.stream("POST", "/api/generate", json=payload, timeout=None) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield json.loads(line)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict:
        """Generate a complete (non-streaming) response via Ollama's chat API.

        Unlike /api/generate (a raw text-completion endpoint), /api/chat takes
        structured {role, content} turns and applies the model's own chat
        template — this avoids the model echoing literal "User:"/"Assistant:"
        labels back, which happens when turns are flattened into plain text.
        """
        client = await self._get_client()
        payload: dict = {
            "model": model or settings.ollama_default_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        resp = await client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {"response": data.get("message", {}).get("content", "")}

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[dict, None]:
        """Stream a chat completion, yielding each token chunk as a dict."""
        client = await self._get_client()
        payload: dict = {
            "model": model or settings.ollama_default_model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with client.stream("POST", "/api/chat", json=payload, timeout=None) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                yield {
                    "response": data.get("message", {}).get("content", ""),
                    "done": data.get("done", False),
                }

    # -- Embeddings --

    async def generate_embedding(self, text: str, model: str | None = None) -> list[float]:
        """Generate an embedding vector for the given text."""
        client = await self._get_client()
        resp = await client.post(
            "/api/embeddings",
            json={
                "model": model or settings.ollama_embedding_model,
                "prompt": text,
            },
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


# --- ModelManager (DB-decoupled) ---


class ModelManager:
    """High-level manager for owner-specific model lifecycle.

    Unlike the apps/api version, this does NOT query the database.
    The caller passes owner_name and language directly.
    """

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or OllamaClient()

    def _owner_model_name(self, owner_id: str) -> str:
        return f"replica-{owner_id[:12]}"

    def _build_system_prompt(self, owner_name: str, language: str, additions: str = "") -> str:
        return OWNER_SYSTEM_PROMPT_TEMPLATE.format(
            owner_name=owner_name,
            language=language,
            additional_instructions=additions,
        ).strip()

    def _build_modelfile(
        self,
        base_model: str,
        system_prompt: str,
        temperature: float = 0.7,
    ) -> str:
        escaped = system_prompt.replace('"', '\\"')
        return (
            f"FROM {base_model}\n"
            f'SYSTEM "{escaped}"\n'
            f"PARAMETER temperature {temperature}\n"
            f"PARAMETER top_p 0.9\n"
        )

    # -- Auto-pull --

    async def ensure_base_model(self) -> list[dict]:
        """Pull the default base model if it's not already present."""
        model = settings.ollama_default_model
        models = await self.client.list_models()
        model_names = [m.get("name", "") for m in models]

        if any(model in name for name in model_names):
            logger.info("Base model %s already available", model)
            return [{"status": "already_available", "model": model}]

        logger.info("Pulling base model %s ...", model)
        progress: list[dict] = []
        async for update in self.client.pull_model(model):
            progress.append(update)
            if status_msg := update.get("status"):
                logger.info("Pull %s: %s", model, status_msg)
        return progress

    # -- Owner model lifecycle (DB-free) --

    async def create_owner_model(
        self,
        owner_id: str,
        owner_name: str,
        language: str,
        additions: str = "",
        base_model: str | None = None,
    ) -> dict:
        """Create a custom Ollama model for a specific owner.

        Unlike the apps/api version, owner_name and language are passed directly
        instead of being looked up from the database.
        """
        model_name = self._owner_model_name(owner_id)
        system_prompt = self._build_system_prompt(
            owner_name=owner_name,
            language=language,
            additions=additions,
        )
        modelfile = self._build_modelfile(
            base_model=base_model or settings.ollama_default_model,
            system_prompt=system_prompt,
        )

        logger.info("Creating owner model %s for %s", model_name, owner_name)
        progress: list[dict] = []
        async for update in self.client.create_model(model_name, modelfile):
            progress.append(update)

        return {
            "model_name": model_name,
            "owner_id": owner_id,
            "system_prompt": system_prompt,
            "progress": progress,
        }

    async def update_system_prompt(
        self,
        owner_id: str,
        owner_name: str,
        language: str,
        additions: str = "",
        base_model: str | None = None,
    ) -> dict:
        """Recreate the owner's model with additional instructions appended."""
        model_name = self._owner_model_name(owner_id)
        system_prompt = self._build_system_prompt(
            owner_name=owner_name,
            language=language,
            additions=additions,
        )
        modelfile = self._build_modelfile(
            base_model=base_model or settings.ollama_default_model,
            system_prompt=system_prompt,
        )

        logger.info("Updating model %s with new instructions", model_name)
        progress: list[dict] = []
        async for update in self.client.create_model(model_name, modelfile):
            progress.append(update)

        return {
            "model_name": model_name,
            "owner_id": owner_id,
            "system_prompt": system_prompt,
            "progress": progress,
        }

    async def get_model_info(self, owner_id: str) -> dict | None:
        """Get details about the owner's custom model, or None if it doesn't exist."""
        model_name = self._owner_model_name(owner_id)
        try:
            info = await self.client.show_model(model_name)
            return {"model_name": model_name, **info}
        except httpx.HTTPStatusError:
            return None
