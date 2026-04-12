---
paths:
  - "apps/api/tests/**"
  - "**/*.test.ts"
  - "**/*.test.tsx"
  - "**/*.spec.ts"
---

## Testing Rules

- Python tests use `pytest` with `pytest-asyncio` for async tests.
- TypeScript tests (when added) should use Vitest.
- Test files mirror the source structure: `app/routers/users.py` → `tests/test_users.py`.
- Use factories or fixtures for test data — never hardcode IDs or timestamps.
- Each test must be independent and not rely on execution order.
