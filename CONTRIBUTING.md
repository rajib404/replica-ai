# Contributing to Replica AI

## Local Development Setup

### Prerequisites

- Node.js >= 20, npm >= 10
- Python >= 3.11 with `venv`
- Docker & Docker Compose
- `ruff` (Python linter/formatter)
- `libmagic` (for file upload validation &mdash; `brew install libmagic` on macOS)

### First-time setup

```bash
make install        # npm install + Python venvs for api/ and ai/
make env            # copy .env.example files
make docker-up      # start Postgres, Redis, Qdrant, Ollama
make db-migrate     # run Prisma migrations
make db-seed        # seed test data (optional)
make dev            # start all apps
```

### Running individual services

```bash
# Frontend only
cd apps/web && npm run dev

# API backend only
cd apps/api && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# AI service only
cd apps/ai && source .venv/bin/activate && uvicorn app.main:app --reload --port 8100
```

### Running tests

```bash
# API tests
cd apps/api && pytest
cd apps/api && pytest -v tests/test_health.py   # single file
cd apps/api && pytest -m unit                    # unit tests only

# AI service tests
cd apps/ai && pytest

# TypeScript lint + type check
make lint
make type-check
```

## Branch Naming

Use the format: `<type>/<short-description>`

| Type | Use for |
|------|---------|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `refactor/` | Code restructuring |
| `docs/` | Documentation changes |
| `test/` | Adding or fixing tests |
| `chore/` | Build, CI, dependency updates |

Examples: `feat/family-chat`, `fix/voice-timeout`, `docs/api-reference`

## Pull Request Process

1. Create a branch from `main`
2. Make your changes with tests
3. Run `make lint && make type-check` locally
4. Push and open a PR against `main`
5. Ensure CI passes (lint, type-check, test)
6. Request review

### PR checklist

- [ ] Tests added/updated for the change
- [ ] `make lint` passes
- [ ] `make type-check` passes
- [ ] No hardcoded secrets or URLs
- [ ] Pydantic models updated if API contract changed
- [ ] Migration added if schema changed (`make db-migrate`)

## Coding Standards

Full standards are documented in [CLAUDE.md](CLAUDE.md). Key rules:

### TypeScript / Next.js (`apps/web`)

- Server components by default. Only add `"use client"` for interactivity.
- Absolute imports via `@/` prefix.
- UI primitives from shadcn/ui in `src/components/ui/`.
- Use `cn()` for conditional class names.
- No `useEffect` for data fetching &mdash; fetch in server components.
- Shared types from `@replica-ai/shared`.

### Python / FastAPI (`apps/api`, `apps/ai`)

- All route handlers must be `async def`.
- Pydantic v2 models for all request/response validation.
- Type hints mandatory on all function signatures.
- Config from `app.core.config.settings` &mdash; never read env vars directly.
- `ruff` for linting/formatting, `mypy` for type checking.
- `apps/api` calls `apps/ai` via `app/core/ai_client.py` &mdash; never import AI code directly.

### Database

- Schema defined in Prisma (`packages/db/prisma/schema.prisma`).
- Migrations via Prisma: `make db-migrate`.
- Python backend uses SQLAlchemy models that mirror the Prisma schema.

## Adding a New Feature

The typical pattern for a new feature:

### 1. Backend (apps/api)

```
apps/api/
├── app/routers/<feature>.py    # API endpoints
├── app/services/<feature>.py   # Business logic
├── app/models/<feature>.py     # SQLAlchemy + Pydantic models
└── tests/test_<feature>.py     # Tests
```

Register the router in `app/main.py`.

### 2. AI Service (apps/ai) &mdash; if the feature needs AI

```
apps/ai/
├── app/routers/<feature>.py
├── app/services/<feature>.py
└── tests/test_<feature>.py
```

Add an endpoint in `apps/ai`, then call it from `apps/api` via `ai_client.py`.

### 3. Frontend (apps/web)

```
apps/web/src/
├── app/<feature>/page.tsx       # Route page (server component)
├── components/<Feature>.tsx     # UI components
└── lib/<feature>.ts             # API client helpers
```

### 4. Shared types (packages/shared)

If the feature introduces types used by both frontend and backend, add them to `packages/shared/src/` and export from `index.ts`.

## Environment Variables

All config uses env vars. See `.env.example` at root and in each app. Never commit real secrets &mdash; use the `.env.example` pattern with placeholder values.

## Questions?

Open an issue or check [CLAUDE.md](CLAUDE.md) for architectural context.
