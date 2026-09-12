# AI Service

Standalone FastAPI service that owns all AI/ML functionality: Ollama, Qdrant, embeddings, RAG, knowledge ingestion, and file storage.

## Quick Start

```bash
cd apps/ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8100
```

## Running Tests

```bash
pytest
pytest -v tests/test_health.py
```

## Linting

```bash
ruff check .
ruff format .
mypy app
```

## Architecture

- **Zero PostgreSQL dependency** — all vector data stored in Qdrant payloads
- Content previews stored alongside embeddings for self-contained RAG
- Background tasks tracked via shared Redis
- File storage on local filesystem under `./storage/`

## Adding a New Router

1. Create `app/routers/<resource>.py` with an `APIRouter`.
2. Add business logic in `app/services/<resource>.py`.
3. Register the router in `app/main.py`.
4. Add tests in `tests/test_<resource>.py`.
