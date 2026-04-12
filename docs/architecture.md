# Architecture

## System Overview

Replica AI follows a client-server architecture with a clear separation between the frontend (Next.js) and backend (FastAPI).

```
┌─────────────┐     HTTP/REST     ┌─────────────┐
│   Next.js   │ ───────────────▶  │   FastAPI    │
│   (web)     │                   │   (api)      │
└─────────────┘                   └──────┬───────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │              │              │
                    ┌─────▼────┐  ┌──────▼─────┐ ┌─────▼────┐
                    │ PostgreSQL│  │   Redis    │ │  Qdrant  │
                    │   (db)   │  │  (cache)   │ │ (vectors)│
                    └──────────┘  └────────────┘ └──────────┘
                                                       │
                                                 ┌─────▼────┐
                                                 │  Ollama   │
                                                 │  (LLM)   │
                                                 └──────────┘
```

## Data Flow

1. User interacts with the Next.js frontend (server components by default).
2. Frontend makes API calls to FastAPI backend.
3. Backend handles business logic, queries PostgreSQL, caches in Redis.
4. For AI features: backend generates embeddings, stores/queries Qdrant, and calls Ollama for inference.

## Key Principles

- **API-first:** Frontend never accesses databases directly.
- **Server components by default:** Minimize client-side JavaScript.
- **Type safety end-to-end:** Shared types in `packages/shared` used by both TS apps.
- **Infrastructure as code:** All services defined in `docker-compose.yml`.
