# Replica AI — Project Context

## Overview

Replica AI is a full-stack AI application built as a Turborepo monorepo. It combines a Next.js frontend, FastAPI backend, and supporting infrastructure (PostgreSQL, Redis, Qdrant, Ollama).

## Tech Stack

- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui
- **Backend:** FastAPI (Python 3.11+), Pydantic v2, SQLAlchemy 2.0 (async)
- **Database:** PostgreSQL 16 via Prisma (TypeScript) and SQLAlchemy (Python)
- **Cache:** Redis 7
- **Vector DB:** Qdrant
- **LLM Runtime:** Ollama (local models)
- **Monorepo:** Turborepo with npm workspaces

## Project Structure

```
replica-ai/
├── apps/
│   ├── web/                  # Next.js 14 App Router
│   │   ├── src/
│   │   │   ├── app/          # App Router pages & layouts
│   │   │   ├── components/   # React components
│   │   │   │   └── ui/       # shadcn/ui components
│   │   │   ├── lib/          # Utilities (cn, fetchers, etc.)
│   │   │   └── styles/       # Global CSS
│   │   └── public/           # Static assets
│   ├── api/                  # FastAPI backend (auth, DB, orchestration)
│   │   ├── app/
│   │   │   ├── core/         # Config, dependencies, AI client
│   │   │   ├── models/       # SQLAlchemy / Pydantic models
│   │   │   ├── routers/      # API route handlers
│   │   │   └── services/     # Business logic (DB-only)
│   │   └── tests/
│   └── ai/                   # Standalone AI/ML service (port 8100)
│       ├── app/
│       │   ├── core/         # Config, Qdrant, storage, task tracker
│       │   ├── models/       # Pydantic request/response models
│       │   ├── routers/      # AI endpoint handlers
│       │   └── services/     # LLM engine, search, knowledge ingestion
│       └── tests/
├── packages/
│   ├── shared/               # Shared TypeScript types & constants
│   │   └── src/
│   └── db/                   # Prisma schema & client
│       ├── prisma/
│       └── src/
├── docs/                     # Architecture docs, session logs
├── .claude/
│   └── rules/                # Path-scoped Claude rules
├── docker-compose.yml        # PostgreSQL, Redis, Qdrant, Ollama
├── Makefile                  # Dev commands
└── turbo.json                # Turborepo config
```

### Service Responsibilities

- **`apps/api` (port 8000):** Auth, users, owners, conversations, threads/messages, PostgreSQL, WebSocket handler. Calls `apps/ai` for all AI operations.
- **`apps/ai` (port 8100):** Ollama, Qdrant, embeddings, RAG, knowledge processing, file storage, background tasks. Zero PostgreSQL dependency.

## Commands

```bash
make dev            # Start infra + all apps in dev mode
make build          # Build everything
make install        # Install all deps (npm + Python venv)
make docker-up      # Start Docker services only
make docker-down    # Stop Docker services
make db-migrate     # Run Prisma migrations
make db-seed        # Seed database
make lint           # Lint all code (TS + Python)
make type-check     # Type check all code
make format         # Format all code
make env            # Copy .env.example files
```

## Coding Standards

### General

- All sensitive configuration MUST use environment variables. Never hardcode secrets, URLs, or credentials.
- Use absolute imports everywhere. No relative imports beyond `./` within the same directory.
- Every new feature needs both frontend and backend changes coordinated.

### TypeScript / Next.js (`apps/web`)

- Use **server components by default**. Only add `"use client"` when you need interactivity (event handlers, hooks, browser APIs).
- Absolute imports via `@/` prefix (maps to `src/`).
- Components go in `src/components/`. UI primitives from shadcn/ui go in `src/components/ui/`.
- Use `cn()` from `@/lib/utils` for conditional class names.
- All data fetching in server components or route handlers — no `useEffect` for data fetching.
- Shared types come from `@replica-ai/shared`, not redefined locally.

### Python / FastAPI (`apps/api` and `apps/ai`)

- All API routes go through FastAPI routers in `app/routers/`.
- Use Pydantic v2 models for request/response validation.
- Use `pydantic-settings` for configuration (reads from env vars).
- Async everywhere — use `async def` for route handlers and service functions.
- Type hints are mandatory on all function signatures.
- Use `ruff` for linting/formatting, `mypy` for type checking.
- `apps/api` calls `apps/ai` via `app/core/ai_client.py` — never import AI service code directly.

### Database (`packages/db`)

- Schema defined in Prisma (`packages/db/prisma/schema.prisma`).
- Always use `@map` for snake_case table/column names in Prisma.
- The singleton Prisma client is exported from `@replica-ai/db`.
- For the Python backend, use SQLAlchemy models that mirror the Prisma schema.

### Shared Package (`packages/shared`)

- All cross-boundary types (used by both web and api) live here.
- Export everything from `src/index.ts`.
- Keep this package dependency-free (types and constants only).

## Architecture Decisions

- **API-first:** The web app never accesses the database directly. All data flows through the FastAPI backend.
- **Server components by default:** Client components are the exception, not the rule.
- **Prisma for migrations, SQLAlchemy for Python:** Prisma owns the schema and migrations. The Python backend reads/writes via SQLAlchemy models that mirror it.
- **Vector search via Qdrant:** Embeddings stored in Qdrant, not PostgreSQL.
- **Local LLM via Ollama:** No external LLM API calls in development.
- **CPU-only inference:** All ML models (Ollama, Resemblyzer, faster-whisper) run on CPU. No GPU/CUDA dependency. Voice embeddings use Resemblyzer's pretrained speaker encoder (~40 MB, CPU). Audio transcription uses faster-whisper `base` model with `int8` quantization on CPU.

## Environment Variables

All services read from `.env` files. See `.env.example` at root and in each app for the full list. Key variables:

| Variable | Used By | Description |
|---|---|---|
| `DATABASE_URL` | db, api | PostgreSQL connection string |
| `REDIS_URL` | api, ai | Redis connection string |
| `AI_SERVICE_URL` | api | AI service endpoint (default: http://localhost:8100) |
| `QDRANT_HOST` / `QDRANT_PORT` | ai | Qdrant vector DB |
| `OLLAMA_BASE_URL` | ai | Ollama LLM endpoint |
| `NEXT_PUBLIC_API_URL` | web | FastAPI URL (client-side) |
| `CORS_ORIGINS` | api, ai | Allowed CORS origins |

## Implementation Status

All phases complete. v1.0.0 tagged 2026-04-09.

### Feature Summary (24 API routers, 4 WebSocket endpoints)

- **Core:** Auth (JWT + refresh), chat (streaming WS), knowledge pipeline, RAG with graceful degradation
- **Voice & Video:** STT (faster-whisper), TTS (Piper), voice chat (WS), video calls (WS), voice/face verification
- **Family Access:** invite codes, QR codes, per-member rules, legacy mode, family chat (WS)
- **Intelligence:** personality learning, emotion detection, fine-tuning, self-learning
- **External LLM:** multi-provider, budget tracking, auto-learn
- **Web Browsing:** URL fetch, search, page monitors
- **Billing:** Stripe integration, survival mode, auto-pay
- **Sync:** multi-instance registration, push/pull, conflict resolution
- **Multilingual:** 14 languages, Ollama + DeepL/Google translation
- **Push Notifications:** VAPID-based web push
- **Security:** 2FA (TOTP), AES-256-GCM encryption at rest, audit logging, per-category rate limiting, MIME validation, security headers, data export/deletion
- **Infrastructure:** Docker prod stack (10 services), nginx, PgBouncer, Let's Encrypt, CI/CD, deploy scripts, backup/restore

## Production Operations

### Always pass `--env-file` with docker compose on production

The production secrets live in `.env.production`. Docker compose does **not** load it automatically — it only auto-loads a file literally named `.env`. The deploy/update scripts pass `--env-file` explicitly, but bare manual commands do not.

**Always run manual docker compose commands like this:**
```bash
docker compose -f /opt/replica-ai/docker-compose.prod.yml --env-file /opt/replica-ai/.env.production <command>
```

Running without `--env-file` causes services to start with wrong or missing secrets (e.g. `QDRANT_API_KEY` resolves to empty string), which leads to auth failures between containers even though `.env.production` looks correct.

This applies to: `up`, `up --force-recreate`, `restart`, `exec`, `logs`, `ps`, `down` — any command where the correct env matters for the operation or the resulting container state.

### Running migrations on production

Migrations must be created locally first, then deployed:

1. **Locally:** `make db-migrate` (runs `prisma migrate dev`) — generates the SQL file in `packages/db/prisma/migrations/`
2. **Commit & push** the migration file
3. **On server:** `sudo ./scripts/update.sh` — applies migrations via `prisma migrate deploy` and does a rolling restart

Never run `prisma migrate dev` on production (it can reset the database). The `update.sh` script uses `migrate deploy` which only applies pending migrations safely.

## References

@docs/architecture.md
@docs/implementation-plan.md
@docs/api-reference.md
@docs/websocket-protocol.md
@docs/api-errors.md
@docs/deployment.md
@docs/integration-test-checklist.md
@docs/launch-checklist.md
