# Pre-Launch Checklist

Security and performance audit for Replica AI v1.0.0. Items are marked based on code audit results.

**Legend:** PASS = verified in code, NEEDS-VERIFICATION = requires runtime/manual check

---

## Security Checklist

### Network & Infrastructure

- [x] **PASS** &mdash; AI service (port 8100) not exposed to host in `docker-compose.prod.yml`
- [x] **PASS** &mdash; Only nginx exposes ports 80/443; all other services on `replica_internal` network
- [x] **PASS** &mdash; `replica_internal` network has `internal: true` (no outbound internet)
- [x] **PASS** &mdash; Services needing egress (api, ai, ollama, certbot, piper) are on `replica_egress`
- [ ] **NEEDS-VERIFICATION** &mdash; SSL certificate valid and auto-renewing (certbot)
  - Check: `docker compose -f docker-compose.prod.yml exec certbot certbot certificates`
- [ ] **NEEDS-VERIFICATION** &mdash; nginx TLS config scores A+ on SSL Labs
  - Check: `https://www.ssllabs.com/ssltest/`
- [x] **PASS** &mdash; HSTS enabled with 2-year max-age, includeSubDomains, preload
  - File: `apps/api/app/core/security_middleware.py`

### Authentication & Authorization

- [x] **PASS** &mdash; JWT tokens with configurable expiry (60min access, 30day refresh)
  - File: `apps/api/app/core/config.py`
- [x] **PASS** &mdash; bcrypt password hashing with cost factor 12
- [x] **PASS** &mdash; 2FA (TOTP) support with configurable window for clock drift
- [x] **PASS** &mdash; WebSocket authentication required on all 4 endpoints
  - File: `docs/websocket-protocol.md` &mdash; token via query param or first message
- [ ] **NEEDS-VERIFICATION** &mdash; JWT secret key is strong and unique in production `.env`
  - Check: ensure `JWT_SECRET_KEY` is not the default `CHANGE-ME-IN-PRODUCTION`

### Encryption

- [x] **PASS** &mdash; AES-256-GCM encryption at rest with PBKDF2 key derivation
  - File: `apps/api/app/core/config.py` (600,000 iterations, 16-byte salt)
- [ ] **NEEDS-VERIFICATION** &mdash; `ENCRYPTION_MASTER_KEY` is set and backed up securely
  - Loss of master key = unrecoverable encrypted data
- [x] **PASS** &mdash; Encryption key and master key sourced from environment variables, never hardcoded

### Input Validation

- [x] **PASS** &mdash; Pydantic v2 models validate all request/response schemas
- [x] **PASS** &mdash; File upload extension whitelist per category (audio, video, document, image)
  - File: `apps/api/app/core/request_limits.py`
- [x] **PASS** &mdash; File upload MIME-type magic-number validation (python-magic)
  - File: `apps/api/app/core/request_limits.py`
- [x] **PASS** &mdash; Request body size limit middleware (550 MB global cap)
- [x] **PASS** &mdash; Per-category upload size limits (audio 50MB, video 500MB, document 25MB, image 10MB)

### Rate Limiting

- [x] **PASS** &mdash; Per-IP token-bucket rate limiting enabled by default
- [x] **PASS** &mdash; Category-specific rate limits enforced:
  - Auth: 10/min, Chat: 60/min, Upload: 20/min, Search: 60/min, Billing: 20/min, General: 100/min
  - File: `apps/api/app/core/security_middleware.py`
- [x] **PASS** &mdash; 429 response includes `Retry-After` header
- [ ] **NEEDS-VERIFICATION** &mdash; nginx-level rate limiting also configured
  - Check: `nginx/conf.d/` for `limit_req_zone` directives

### Security Headers

- [x] **PASS** &mdash; Content-Security-Policy (default-src 'none')
- [x] **PASS** &mdash; X-Frame-Options: DENY
- [x] **PASS** &mdash; X-Content-Type-Options: nosniff
- [x] **PASS** &mdash; Referrer-Policy: no-referrer
- [x] **PASS** &mdash; Permissions-Policy: restrictive (no geolocation, microphone, camera, payment)
- [x] **PASS** &mdash; Cross-Origin-Opener-Policy: same-origin
- [x] **PASS** &mdash; Cross-Origin-Resource-Policy: same-origin

### Audit & Compliance

- [x] **PASS** &mdash; Audit logging enabled by default with configurable retention
  - File: `apps/api/app/core/config.py` (`audit_log_enabled`, `audit_log_retention_days`)
- [x] **PASS** &mdash; Data export endpoint (`/api/security/export`)
- [x] **PASS** &mdash; Account deletion with confirmation phrase
- [x] **PASS** &mdash; X-Request-Id correlation on all responses

### Secrets Management

- [ ] **NEEDS-VERIFICATION** &mdash; No secrets in git history
  - Check: `git log --all --oneline -S 'CHANGE-ME' -- '*.py' '*.ts' '*.env'`
- [ ] **NEEDS-VERIFICATION** &mdash; `.env` files are in `.gitignore`
  - Check: `grep '\.env' .gitignore`
- [ ] **NEEDS-VERIFICATION** &mdash; Production `.env` uses strong, unique values for:
  - `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, `ENCRYPTION_MASTER_KEY`
  - `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
  - `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
  - `VAPID_PRIVATE_KEY`
  - `QDRANT_API_KEY`

---

## Performance Checklist

### Database

- [x] **PASS** &mdash; PgBouncer connection pooling configured (20 default pool, 200 max client)
  - File: `docker-compose.prod.yml`
- [x] **PASS** &mdash; Async database access via SQLAlchemy 2.0 + asyncpg
- [ ] **NEEDS-VERIFICATION** &mdash; Database indexes cover common query patterns
  - Check: `EXPLAIN ANALYZE` on owner lookups, thread listings, knowledge searches
- [ ] **NEEDS-VERIFICATION** &mdash; Prisma migrations are up to date (`make db-migrate`)

### Caching

- [x] **PASS** &mdash; Redis with AOF persistence and LRU eviction (512MB cap)
- [x] **PASS** &mdash; Graceful degradation when Redis is unavailable (`cache_optional: true`)

### AI / ML

- [x] **PASS** &mdash; CPU-only inference (no GPU dependency)
- [x] **PASS** &mdash; faster-whisper with int8 quantization for STT
- [x] **PASS** &mdash; Graceful degradation when Qdrant is unavailable (`rag_optional: true`)
- [x] **PASS** &mdash; Ollama retry with exponential backoff (3 attempts)
- [ ] **NEEDS-VERIFICATION** &mdash; Ollama model pre-pulled on production host
  - Check: `docker compose exec ollama ollama list`
- [ ] **NEEDS-VERIFICATION** &mdash; STT model cached (first request downloads ~150MB)

### Resource Limits

- [x] **PASS** &mdash; Docker memory limits set for all services:
  - nginx: 256MB, web: 1GB, api: 2GB, ai: 4GB, postgres: 2GB, redis: 768MB, qdrant: 2GB, ollama: 8GB
  - File: `docker-compose.prod.yml`
- [x] **PASS** &mdash; Docker CPU limits set for all services
- [x] **PASS** &mdash; Log rotation configured (20MB max, 5 files)
- [ ] **NEEDS-VERIFICATION** &mdash; Host has sufficient resources for all containers
  - Minimum: 16GB RAM, 4 CPU cores, 50GB disk
  - Check: `docker stats` under load

### Concurrency

- [x] **PASS** &mdash; Gunicorn workers configurable via env (api: 4 default, ai: 2 default)
- [x] **PASS** &mdash; Gunicorn timeout configurable (api: 120s, ai: 300s)
- [ ] **NEEDS-VERIFICATION** &mdash; WebSocket connections scale under concurrent users
  - Load test: use `locust` (available via `pip install -e ".[load]"` in apps/api)

### Health Checks

- [x] **PASS** &mdash; Health checks configured for all Docker services with intervals + retries
- [x] **PASS** &mdash; Start periods configured for slow-starting services (web: 30s, api: 60s, ai: 60s, postgres: 30s, ollama: 60s)
- [ ] **NEEDS-VERIFICATION** &mdash; `/api/health/detailed` reports correct status for all dependencies

### Monitoring

- [ ] **NEEDS-VERIFICATION** &mdash; Container log aggregation configured (ELK, Loki, or CloudWatch)
- [ ] **NEEDS-VERIFICATION** &mdash; Alerting set up for container restarts, high memory, disk space
- [ ] **NEEDS-VERIFICATION** &mdash; Backup cron job running (PostgreSQL + Qdrant snapshots)
  - See: [Deployment Guide](deployment.md) for backup configuration

---

## Pre-Deploy Final Steps

- [ ] Run full integration test checklist: [integration-test-checklist.md](integration-test-checklist.md)
- [ ] Run `make lint && make type-check` &mdash; zero errors
- [ ] Run `cd apps/api && pytest` &mdash; all tests pass
- [ ] Run `cd apps/ai && pytest` &mdash; all tests pass
- [ ] Review `docker-compose.prod.yml` env vars against `.env.production.example`
- [ ] Tag release: `git tag -a v1.0.0 -m "Replica AI v1.0.0"`
- [ ] Deploy using `scripts/deploy.sh` (see [Deployment Guide](deployment.md))
- [ ] Verify health endpoint returns 200 on production URL
- [ ] Verify WebSocket connection works on production URL (wss://)
