"""OpenAPI metadata: tags, description, contact, license.

Centralising this keeps ``main.py`` focused on wiring and lets us
evolve the docs without touching the app factory.
"""

from __future__ import annotations

API_DESCRIPTION = """\
Replica AI — FastAPI backend.

This service owns authentication, user/owner/conversation data, and
orchestration. It delegates all AI work (Ollama, Qdrant, RAG, embeddings)
to the separate **AI service** (apps/ai, port 8100) over HTTP.

## Error format

All errors return a consistent envelope:

```json
{
  "error": {
    "code": "AUTH_FAILED",
    "message": "Authentication failed.",
    "details": {}
  }
}
```

See `docs/api-errors.md` for the full list of error codes.

## WebSocket protocol

REST endpoints documented below cover synchronous operations. Streaming
chat, voice, and video calls use WebSockets — see
`docs/websocket-protocol.md` for the full protocol specification.

## Authentication

Most endpoints require a bearer JWT in the `Authorization` header:

    Authorization: Bearer eyJhbGciOi...

Tokens are obtained via `POST /api/auth/login` and rotated with
`POST /api/auth/refresh`. Access tokens last 1 hour; refresh tokens
last 30 days.

## Rate limits

Global per-IP rate limits apply:

- `/api/auth/*` and `/api/security/2fa/*`: 10 req/min
- `/api/*` (everything else): 100 req/min

429 responses carry a `Retry-After` header.
"""

TAGS_METADATA = [
    {
        "name": "Health",
        "description": (
            "System status and metrics. `/api/health` is safe to call from "
            "load balancers — it never raises and always returns JSON. "
            "`/api/health/detailed` exposes disk, uptime, and queue metrics."
        ),
    },
    {
        "name": "Auth",
        "description": (
            "Login, signup, token refresh, password reset, and voice/face "
            "enrollment/verification. Bearer JWTs use RS256."
        ),
    },
    {
        "name": "Chat",
        "description": (
            "Conversation threads, message history, and message send. "
            "Streaming responses are available via the WebSocket endpoint "
            "`/ws/chat/{owner_id}` — see `docs/websocket-protocol.md`."
        ),
    },
    {
        "name": "Voice",
        "description": (
            "Voice verification (enroll / check) and the voice chat WebSocket "
            "pipeline (STT → LLM → TTS)."
        ),
    },
    {
        "name": "Video",
        "description": (
            "Face verification and the video call WebSocket pipeline. Video "
            "messages reuse the knowledge ingestion pipeline."
        ),
    },
    {
        "name": "Knowledge",
        "description": (
            "Ingest text, audio, video, and documents into the owner's "
            "knowledge base. Files are processed asynchronously by the AI "
            "service and surfaced via RAG during chat."
        ),
    },
    {
        "name": "Search",
        "description": "Semantic and full-text search over the owner's knowledge.",
    },
    {
        "name": "Access",
        "description": (
            "Family access control, invitations, and legacy-mode "
            "configuration (post-inactivity access for trusted family)."
        ),
    },
    {
        "name": "Billing",
        "description": (
            "Stripe integration for the hosting subscription and self-"
            "preservation countdowns when payment lapses."
        ),
    },
    {
        "name": "Model",
        "description": (
            "Local Ollama model management: list, pull, create per-owner "
            "custom models, and view details."
        ),
    },
    {
        "name": "External LLM",
        "description": (
            "Configure and route queries to external LLM providers (OpenAI, "
            "Anthropic, etc.) with per-owner budgets."
        ),
    },
    {
        "name": "Sync",
        "description": (
            "Multi-instance replication — keep a replica's state in sync "
            "across self-hosted installations."
        ),
    },
    {
        "name": "Security",
        "description": (
            "Encryption status, audit log, two-factor authentication, data "
            "export, and account deletion."
        ),
    },
    {
        "name": "Language",
        "description": "Per-owner preferred language and translation settings.",
    },
    {
        "name": "Personality",
        "description": (
            "Personality tracking — analyses owner messages and exposes the "
            "learned traits that shape replica behaviour."
        ),
    },
    {
        "name": "Learning",
        "description": (
            "Self-learning configuration: nightly knowledge refresh, topic "
            "discovery, and consolidation."
        ),
    },
    {
        "name": "Finetune",
        "description": (
            "Fine-tuning pipeline: build training data from owner messages, "
            "kick off training runs, and roll back."
        ),
    },
    {
        "name": "Web Browse",
        "description": "On-demand and scheduled web browsing for research and monitoring.",
    },
    {
        "name": "Instances",
        "description": "Register and heartbeat self-hosted replica instances.",
    },
]

CONTACT_INFO = {
    "name": "Replica AI",
    "url": "https://github.com/alex-replica-ai/replica-ai",
}

LICENSE_INFO = {
    "name": "Proprietary",
}
