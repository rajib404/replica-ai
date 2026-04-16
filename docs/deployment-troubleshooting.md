# Deployment Troubleshooting

Real-world issues encountered during VPS deployment and how to fix them.
The `scripts/deploy.sh` script now handles most of these automatically, but
this document captures the underlying problems for manual debugging.

---

## Pre-flight: DNS

Before running `deploy.sh`, the DNS A record for your domain MUST point to
the VPS's public IP address. Verify with:

```bash
dig +short <your-domain> @8.8.8.8
```

Without correct DNS, certbot (Let's Encrypt) cannot obtain a TLS certificate
and the deploy will fail at the certbot step.

---

## Issue 1: `NEXT_PUBLIC_API_URL` not baked into Next.js bundle

**Symptom:** Browser tries to call `http://localhost:8000` instead of
`https://<your-domain>`. Health page works (server-side) but client-side
API calls fail.

**Root cause:** Next.js inlines `NEXT_PUBLIC_*` env vars at **build time**,
not runtime. The Dockerfile has `ARG NEXT_PUBLIC_API_URL` but
`docker-compose.prod.yml` must pass it as a build arg.

**Fix:** `docker-compose.prod.yml` now includes:
```yaml
web:
  build:
    args:
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
```

If you change `NEXT_PUBLIC_API_URL` after deploy, you must rebuild:
```bash
docker compose -f docker-compose.prod.yml build --no-cache web
docker compose -f docker-compose.prod.yml up -d web
```

---

## Issue 2: `.env` vs `.env.production`

**Symptom:** Containers start without expected env vars, e.g. Redis password
not loaded, services can't connect to one another.

**Root cause:** Docker Compose by default reads `.env` (not
`.env.production`). The deploy script uses `--env-file .env.production`,
but ad-hoc commands like `docker compose ps` without that flag will use
the default `.env`.

**Fix:** `deploy.sh` now creates a symlink: `.env -> .env.production` so
both work. You can also always pass `--env-file .env.production` explicitly.

---

## Issue 3: Qdrant API key + AI service auth

**Symptom:** AI service health shows Qdrant as `unreachable`. Qdrant logs
show `401 Unauthorized` on every `GET /collections`.

**Root causes (multiple):**
1. The AI service's Qdrant client did not pass `api_key` (now fixed in
   `apps/ai/app/core/qdrant.py` and `apps/ai/app/core/config.py`).
2. The compose file did not expose `QDRANT_API_KEY` to the AI service
   (now fixed in `docker-compose.prod.yml`).
3. The qdrant-client library auto-switches to HTTPS when `api_key` is set,
   but Qdrant runs over plain HTTP on the internal network. Pass
   `https=False` explicitly (now fixed).

If the symptom recurs, verify:
```bash
docker compose -f docker-compose.prod.yml exec ai env | grep QDRANT
docker compose -f docker-compose.prod.yml exec qdrant env | grep API_KEY
```
Both must show the same key.

---

## Issue 4: Ollama model not pulled

**Symptom:** Chat doesn't reply. Local Model shows `ok` but no response.

**Root cause:** Fresh Ollama install has no models. The compose file sets
`OLLAMA_DEFAULT_MODEL` but never pulls it.

**Fix:** `deploy.sh` now auto-pulls the model after services come up.

Manual pull:
```bash
docker compose -f docker-compose.prod.yml exec ollama ollama pull gemma2:2b
```

**RAM-aware model selection** (also handled by deploy.sh):
| RAM      | Model                  | Size  |
|----------|------------------------|-------|
| ≥ 16 GB  | `mistral:7b-instruct`  | ~4 GB |
| ≥ 12 GB  | `qwen2.5:3b`           | ~2 GB |
| 8 GB     | `gemma2:2b`            | ~1.6 GB |

The `mistral:7b-instruct` default is too large for 8 GB hosts and will
either OOM or run extremely slowly.

---

## Issue 5: PgBouncer port mismatch

**Symptom:** API logs show `Connection refused` to pgbouncer.

**Root cause:** The `edoburu/pgbouncer` image listens on port `5432`
inside the container by default — not `6432` (the host-side convention).

**Fix:** `docker-compose.prod.yml` sets `DATABASE_URL` to point to
`pgbouncer:5432` (not `:6432`), and the healthcheck also uses `5432`.

---

## Issue 6: Redis URL missing password

**Symptom:** API and AI services can't connect to Redis even though Redis
is healthy.

**Root cause:** `REDIS_URL` was `redis://redis:6379/0` without the password
component, but the Redis server requires auth via `--requirepass`.

**Fix:** `docker-compose.prod.yml` now sets:
```
REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
```

---

## Issue 7: Qdrant healthcheck command unavailable

**Symptom:** Qdrant container reports `unhealthy` even though it is
serving requests.

**Root cause:** The Qdrant image does not include `wget` or `curl`. Only
`bash`, plus `/dev/tcp` redirection, is available.

**Fix:** `docker-compose.prod.yml` healthcheck now uses:
```yaml
test: ["CMD-SHELL", "bash -c ':> /dev/tcp/localhost/6333'"]
```

---

## Issue 8: API container missing system / Python deps

**Symptom:** API container crashes on start with one of:
- `OSError: failed to find libmagic`
- `ModuleNotFoundError: No module named 'cuid2'`

**Fix:** Both are now baked in:
- `apps/api/Dockerfile` installs `libmagic1` via apt
- `apps/api/pyproject.toml` lists `cuid2>=2.0.0`

---

## Issue 9: Web build fails on syntax / lint

**Symptom:** `next build` fails with one of:
- `Expression expected` near `??`/`||`
- `Definition for rule '@typescript-eslint/no-explicit-any' was not found`

**Fix:** Already applied:
- `apps/web/src/app/family/join/page.tsx` parenthesises mixed `??`/`||`
- `apps/web/src/app/sw.ts` uses bare `/* eslint-disable */`

---

## Issue 10: Prisma migration failing inside the internal network

**Symptom:** Migration container can't pull the Prisma engine because the
`replica_internal` Docker network has `internal: true` (no egress).

**Fix:** `deploy.sh` runs the migration through `replica_internal` only
for DB connectivity, but uses the host's network for the npm install.
Alternatively, run the migration from the host using the postgres
container's IP.

---

## Quick Health Check

After any deploy or change:

```bash
# Service status
docker compose -f docker-compose.prod.yml ps

# Detailed health (database, redis, ai, ollama, qdrant)
docker compose -f docker-compose.prod.yml exec api \
    curl -s http://localhost:8000/api/health/detailed | python3 -m json.tool

# Confirm Ollama model is pulled
docker compose -f docker-compose.prod.yml exec ollama ollama list

# Confirm Qdrant is reachable from AI
docker compose -f docker-compose.prod.yml exec ai sh -c \
    'curl -s -i -H "api-key: $QDRANT_API_KEY" http://qdrant:6333/collections'
```

All five top-level statuses (`database`, `redis`, `ai_service`, `ollama`,
`qdrant`) should report `ok`.
