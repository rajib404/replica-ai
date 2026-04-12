---
paths:
  - "apps/api/**"
---

## FastAPI Backend Rules

- All route handlers must be `async def`.
- Use dependency injection via FastAPI's `Depends()`.
- Request/response models must be Pydantic v2 `BaseModel` subclasses.
- Config values come from `app.core.config.settings` — never read env vars directly in route handlers.
- Group routes by domain in `app/routers/` — one file per resource (e.g., `users.py`, `chat.py`).
- Business logic belongs in `app/services/`, not in route handlers.
- All functions must have complete type annotations.
- Use `ruff` rules, not `black` or `flake8`.
