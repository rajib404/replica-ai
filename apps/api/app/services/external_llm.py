"""External LLM gateway: query external providers, manage budgets, sanitize prompts."""

import logging
import re
from datetime import UTC, datetime

from cuid2 import cuid_wrapper
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import get_ai_client
from app.core.config import settings
from app.core.security import decrypt_value, encrypt_value
from app.models.owner import (
    ExternalLLMConfig,
    ExternalLLMUsageLog,
    LLMProvider,
    Owner,
)

logger = logging.getLogger(__name__)
generate_cuid = cuid_wrapper()

# ─── Cost table (USD per 1K tokens) ─────────────────────

COST_TABLE: dict[str, dict[str, tuple[float, float]]] = {
    # provider -> model_prefix -> (prompt_per_1k, completion_per_1k)
    "openai": {
        "gpt-4o": (0.005, 0.015),
        "gpt-4": (0.03, 0.06),
        "gpt-3.5": (0.0005, 0.0015),
        "default": (0.005, 0.015),
    },
    "anthropic": {
        "claude-3-opus": (0.015, 0.075),
        "claude-3-sonnet": (0.003, 0.015),
        "claude-3-haiku": (0.00025, 0.00125),
        "claude-sonnet-4": (0.003, 0.015),
        "claude-opus-4": (0.015, 0.075),
        "default": (0.003, 0.015),
    },
    "google": {
        "gemini-pro": (0.00025, 0.0005),
        "gemini-1.5": (0.00035, 0.00105),
        "default": (0.00035, 0.00105),
    },
    "custom": {
        "default": (0.001, 0.002),
    },
}


def _estimate_cost(
    provider: str, model: str | None, prompt_tokens: int, completion_tokens: int
) -> float:
    provider_table = COST_TABLE.get(provider, COST_TABLE["custom"])
    rate = provider_table.get("default", (0.001, 0.002))
    if model:
        for prefix, r in provider_table.items():
            if prefix != "default" and model.startswith(prefix):
                rate = r
                break
    prompt_cost = (prompt_tokens / 1000) * rate[0]
    completion_cost = (completion_tokens / 1000) * rate[1]
    return round(prompt_cost + completion_cost, 6)


# ─── Privacy Firewall ────────────────────────────────────


class ExternalRequestSanitizer:
    """Strips personal data from prompts before sending to external LLMs."""

    # Patterns to redact
    EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
    SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    CREDIT_CARD_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
    IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

    PATTERNS = [
        (EMAIL_RE, "[EMAIL_REDACTED]"),
        (PHONE_RE, "[PHONE_REDACTED]"),
        (SSN_RE, "[SSN_REDACTED]"),
        (CREDIT_CARD_RE, "[CARD_REDACTED]"),
        (IP_RE, "[IP_REDACTED]"),
    ]

    def __init__(self, owner_name: str | None = None) -> None:
        self._owner_name = owner_name
        self._replacements: list[tuple[str, str]] = []
        if owner_name:
            self._replacements.append((owner_name, "[OWNER_NAME]"))

    def sanitize(self, text: str) -> tuple[str, bool]:
        """Return (sanitized_text, was_modified)."""
        result = text
        modified = False

        # Regex patterns
        for pattern, replacement in self.PATTERNS:
            new_result = pattern.sub(replacement, result)
            if new_result != result:
                modified = True
                result = new_result

        # Owner name
        for original, replacement in self._replacements:
            if original in result:
                result = result.replace(original, replacement)
                modified = True

        return result, modified

    def add_personal_names(self, names: list[str]) -> None:
        """Add additional personal names to redact."""
        for name in names:
            if name and len(name) > 2:
                self._replacements.append((name, "[PERSON_NAME]"))


# ─── External LLM Gateway ───────────────────────────────


class ExternalLLMGateway:
    """Queries external LLM providers with budget management and privacy protection."""

    # -- Config CRUD --

    @staticmethod
    async def create_config(
        owner_id: str,
        provider: str,
        api_key: str,
        model_name: str | None,
        monthly_budget_usd: float,
        daily_budget_usd: float,
        auto_learn: bool,
        db: AsyncSession,
    ) -> ExternalLLMConfig:
        config = ExternalLLMConfig(
            id=generate_cuid(),
            owner_id=owner_id,
            provider=LLMProvider(provider),
            api_key_encrypted=encrypt_value(api_key),
            model_name=model_name,
            monthly_budget_usd=monthly_budget_usd,
            daily_budget_usd=daily_budget_usd,
            auto_learn=auto_learn,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config

    @staticmethod
    async def get_configs(owner_id: str, db: AsyncSession) -> list[ExternalLLMConfig]:
        result = await db.execute(
            select(ExternalLLMConfig).where(ExternalLLMConfig.owner_id == owner_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_config(
        config_id: str, owner_id: str, db: AsyncSession
    ) -> ExternalLLMConfig | None:
        result = await db.execute(
            select(ExternalLLMConfig).where(
                ExternalLLMConfig.id == config_id,
                ExternalLLMConfig.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_config(
        config: ExternalLLMConfig,
        updates: dict,
        db: AsyncSession,
    ) -> ExternalLLMConfig:
        if "api_key" in updates and updates["api_key"]:
            config.api_key_encrypted = encrypt_value(updates.pop("api_key"))
        for key, value in updates.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        await db.commit()
        await db.refresh(config)
        return config

    @staticmethod
    async def delete_config(
        config_id: str, owner_id: str, db: AsyncSession
    ) -> bool:
        config = await ExternalLLMGateway.get_config(config_id, owner_id, db)
        if not config:
            return False
        await db.delete(config)
        await db.commit()
        return True

    # -- Budget management --

    @staticmethod
    async def check_budget(config: ExternalLLMConfig) -> tuple[bool, str | None]:
        """Check if budget allows another query. Returns (ok, warning_or_error)."""
        if config.monthly_budget_usd > 0:
            pct = config.spent_this_month_usd / config.monthly_budget_usd
            if pct >= 1.0:
                return False, "Monthly budget exhausted. Queries disabled until next month."
            if pct >= settings.external_llm_budget_alert_pct:
                return True, f"Budget warning: {pct:.0%} of monthly budget used."
        return True, None

    @staticmethod
    async def record_usage(
        config: ExternalLLMConfig,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        query_text: str | None,
        response_text: str | None,
        was_sanitized: bool,
        db: AsyncSession,
    ) -> ExternalLLMUsageLog:
        log = ExternalLLMUsageLog(
            id=generate_cuid(),
            config_id=config.id,
            owner_id=config.owner_id,
            provider=config.provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            query_text=query_text[:500] if query_text else None,
            response_text=response_text[:500] if response_text else None,
            was_sanitized=was_sanitized,
        )
        db.add(log)
        config.spent_this_month_usd += cost_usd
        await db.commit()
        return log

    @staticmethod
    async def get_usage(
        owner_id: str, db: AsyncSession, config_id: str | None = None, limit: int = 50
    ) -> dict:
        """Get usage summary and logs for an owner."""
        where_clauses = [ExternalLLMUsageLog.owner_id == owner_id]
        if config_id:
            where_clauses.append(ExternalLLMUsageLog.config_id == config_id)

        # Aggregates
        agg = await db.execute(
            select(
                sa_func.coalesce(sa_func.sum(ExternalLLMUsageLog.cost_usd), 0.0),
                sa_func.count(ExternalLLMUsageLog.id),
                sa_func.coalesce(sa_func.sum(ExternalLLMUsageLog.prompt_tokens), 0),
                sa_func.coalesce(sa_func.sum(ExternalLLMUsageLog.completion_tokens), 0),
            ).where(*where_clauses)
        )
        row = agg.one()
        total_cost = float(row[0])
        total_queries = int(row[1])
        total_prompt = int(row[2])
        total_completion = int(row[3])

        # Monthly budget remaining
        configs = await ExternalLLMGateway.get_configs(owner_id, db)
        total_budget = sum(c.monthly_budget_usd for c in configs)
        total_spent = sum(c.spent_this_month_usd for c in configs)
        budget_remaining = max(total_budget - total_spent, 0.0)
        budget_pct = (total_spent / total_budget * 100) if total_budget > 0 else 0.0

        # Recent logs
        result = await db.execute(
            select(ExternalLLMUsageLog)
            .where(*where_clauses)
            .order_by(ExternalLLMUsageLog.created_at.desc())
            .limit(limit)
        )
        logs = list(result.scalars().all())

        return {
            "total_cost_usd": round(total_cost, 4),
            "total_queries": total_queries,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "budget_remaining_monthly": round(budget_remaining, 2),
            "budget_pct_used": round(budget_pct, 1),
            "logs": logs,
        }

    # -- Core query --

    @staticmethod
    async def query_external(
        owner_id: str,
        prompt: str,
        db: AsyncSession,
        config_id: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        learn: bool | None = None,
    ) -> dict:
        """Query an external LLM. Returns response dict."""
        import httpx

        # Pick config
        if config_id:
            config = await ExternalLLMGateway.get_config(config_id, owner_id, db)
        else:
            configs = await ExternalLLMGateway.get_configs(owner_id, db)
            config = next((c for c in configs if c.is_active), None)

        if not config:
            raise ValueError("No active external LLM configuration found.")
        if not config.is_active:
            raise ValueError("This LLM provider is disabled.")

        # Budget check
        ok, budget_msg = await ExternalLLMGateway.check_budget(config)
        if not ok:
            raise ValueError(budget_msg)

        # Sanitize prompt
        owner_result = await db.execute(
            select(Owner.name).where(Owner.id == owner_id)
        )
        owner_name = owner_result.scalar_one_or_none()
        sanitizer = ExternalRequestSanitizer(owner_name=owner_name)
        sanitized_prompt, was_sanitized = sanitizer.sanitize(prompt)

        # Decrypt API key
        api_key = decrypt_value(config.api_key_encrypted)

        # Route to provider
        provider = config.provider.value
        model = config.model_name

        response_text, prompt_tokens, completion_tokens = await _call_provider(
            provider=provider,
            api_key=api_key,
            model=model,
            prompt=sanitized_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Calculate cost
        cost = _estimate_cost(provider, model, prompt_tokens, completion_tokens)

        # Record usage
        await ExternalLLMGateway.record_usage(
            config=config,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            query_text=prompt,
            response_text=response_text,
            was_sanitized=was_sanitized,
            db=db,
        )

        # Auto-learn: ingest the external response into local knowledge
        should_learn = learn if learn is not None else config.auto_learn
        learned = False
        if should_learn and response_text:
            try:
                ai_client = get_ai_client()
                await ai_client.ingest_text(
                    owner_id=owner_id,
                    text=f"[External {provider}] Q: {prompt}\nA: {response_text}",
                    language="en",
                )
                learned = True
            except Exception:
                logger.warning("Failed to auto-learn external response", exc_info=True)

        return {
            "response": response_text,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            "was_sanitized": was_sanitized,
            "learned": learned,
            "budget_warning": budget_msg,
        }

    # -- Monthly budget reset --

    @staticmethod
    async def reset_monthly_budgets(db: AsyncSession) -> int:
        """Reset spent_this_month_usd for all configs. Called on 1st of month."""
        result = await db.execute(
            select(ExternalLLMConfig).where(ExternalLLMConfig.spent_this_month_usd > 0)
        )
        configs = list(result.scalars().all())
        for config in configs:
            config.spent_this_month_usd = 0.0
        await db.commit()
        return len(configs)


# ─── Provider dispatch ───────────────────────────────────


async def _call_provider(
    provider: str,
    api_key: str,
    model: str | None,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, int, int]:
    """Call an external LLM provider. Returns (response_text, prompt_tokens, completion_tokens)."""
    import httpx

    if provider == "openai":
        return await _call_openai(api_key, model or "gpt-4o", prompt, max_tokens, temperature)
    elif provider == "anthropic":
        return await _call_anthropic(api_key, model or "claude-sonnet-4-5-20250929", prompt, max_tokens, temperature)
    elif provider == "google":
        return await _call_google(api_key, model or "gemini-1.5-flash", prompt, max_tokens, temperature)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def _call_openai(
    api_key: str, model: str, prompt: str, max_tokens: int, temperature: float
) -> tuple[str, int, int]:
    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


async def _call_anthropic(
    api_key: str, model: str, prompt: str, max_tokens: int, temperature: float
) -> tuple[str, int, int]:
    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


async def _call_google(
    api_key: str, model: str, prompt: str, max_tokens: int, temperature: float
) -> tuple[str, int, int]:
    import httpx

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return (
            text,
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0),
        )
