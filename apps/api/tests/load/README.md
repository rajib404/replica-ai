# Load tests

[Locust](https://locust.io/) scenarios for the Replica AI FastAPI backend.

## Install

```bash
cd apps/api
pip install -e ".[load]"
```

## Run interactively

```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
```

Then open http://localhost:8089 and choose user count + spawn rate.

## Run headless

```bash
locust -f tests/load/locustfile.py \
    --host http://localhost:8000 \
    --users 50 \
    --spawn-rate 5 \
    --run-time 2m \
    --headless
```

## User classes

| Class                    | Weight | Behavior                                                  |
|--------------------------|--------|-----------------------------------------------------------|
| `OwnerChatUser`          | 5      | Authenticate, chat, ingest text, browse threads.          |
| `KnowledgeIngestionUser` | 2      | Authenticate, then back-to-back text ingest.              |
| `HealthCheckUser`        | 1      | Public health endpoints, baseline liveness signal.        |

## Notes

- Each virtual user calls `/api/auth/setup` once at start. The endpoint
  generates a fresh owner record + JWT pair, so a long run can leave many
  rows behind — use a throwaway database.
- The chat path requires the AI service (`apps/ai` on :8100) to be reachable
  from the API. For pure API-layer profiling, point `AI_SERVICE_URL` at a
  mock or run `apps/ai` with a stubbed LLM backend.
