# Changelog

All notable changes to Replica AI are documented in this file.

## [1.0.0] - 2026-04-09

Initial release. A self-hosted AI companion with local-first inference, voice/video interaction, and end-to-end encryption.

### Core

- **Authentication** &mdash; register, login, JWT access/refresh tokens, session management
- **Chat** &mdash; streaming WebSocket chat with thread management
- **Knowledge Pipeline** &mdash; document ingestion, conversation learning, vector search via Qdrant
- **RAG** &mdash; retrieval-augmented generation with source attribution and graceful degradation

### Voice & Video

- **Speech-to-Text** &mdash; faster-whisper (CPU, int8 quantization) with noise reduction
- **Text-to-Speech** &mdash; Piper TTS via Wyoming protocol
- **Voice Chat** &mdash; full-duplex WebSocket voice calls (STT + LLM + TTS)
- **Video Calls** &mdash; WebSocket video with audio + periodic face frame verification
- **Voice Verification** &mdash; speaker enrollment and verification via Resemblyzer embeddings
- **Face Verification** &mdash; face enrollment and verification via face_recognition

### Family Access

- **Family invites** &mdash; invite codes with configurable expiry
- **QR code invites** &mdash; scannable invite generation
- **Access rules** &mdash; per-member topic restrictions, time limits, content filtering
- **Legacy mode** &mdash; restricted access profile for estate planning
- **Family chat** &mdash; dedicated WebSocket channel for family members

### Intelligence

- **Personality learning** &mdash; owner profiling from conversation patterns
- **Emotion detection** &mdash; real-time emotion analysis in messages
- **Fine-tuning** &mdash; export training pairs, trigger Ollama fine-tuning, version management
- **Self-learning** &mdash; autonomous knowledge acquisition via web research and consolidation

### External LLM

- **Multi-provider support** &mdash; OpenAI, Anthropic, and other providers via configurable backends
- **Budget tracking** &mdash; per-provider monthly spending limits with alerts
- **Auto-learn** &mdash; ingest external LLM responses into local knowledge base

### Web Browsing

- **URL fetch** &mdash; extract and process web page content
- **Web search** &mdash; search the web and process results
- **Page monitors** &mdash; watch URLs for changes with configurable intervals

### Billing

- **Stripe integration** &mdash; subscription checkout, webhook handling, cancellation
- **Survival mode** &mdash; graceful degradation during payment lapses with configurable grace period
- **Auto-pay** &mdash; automatic subscription renewal

### Multi-Instance Sync

- **Instance registration** &mdash; register and discover peer instances
- **State sync** &mdash; push/pull state between instances
- **Conflict resolution** &mdash; detect and resolve divergent state

### Multilingual

- **Language detection** &mdash; automatic input language identification
- **Translation** &mdash; Ollama-based translation with optional DeepL/Google fallback
- **14 supported languages** &mdash; en, es, ar, bn, hi, zh, fr, de, pt, ja, ko, ru, it, tr

### Push Notifications

- **Web Push** &mdash; VAPID-authenticated push delivery
- **Subscription management** &mdash; subscribe, unsubscribe, test endpoints

### Security

- **2FA (TOTP)** &mdash; time-based one-time passwords with QR setup
- **Encryption at rest** &mdash; AES-256-GCM derived from master key (PBKDF2)
- **Audit logging** &mdash; security event tracking with configurable retention
- **Per-category rate limiting** &mdash; token-bucket rate limits for auth, chat, upload, search, billing
- **Security headers** &mdash; HSTS, CSP, X-Frame-Options, CORP, COOP, Permissions-Policy
- **MIME-type validation** &mdash; magic-number verification for all file uploads
- **Data export & deletion** &mdash; GDPR-style data portability and right to erasure
- **Identity challenges** &mdash; in-chat verification prompts for suspicious sessions

### Infrastructure

- **Docker production stack** &mdash; 10-service compose with internal networking, resource limits, health checks
- **nginx reverse proxy** &mdash; TLS termination, WebSocket proxying, Let's Encrypt auto-renewal
- **PgBouncer** &mdash; connection pooling for PostgreSQL
- **CI/CD** &mdash; GitHub Actions for lint, type-check, test, build, deploy
- **Deploy scripts** &mdash; automated production deployment with rollback
- **Backup/restore** &mdash; PostgreSQL + Qdrant snapshot management
- **Graceful degradation** &mdash; chat continues when Qdrant or Redis is unavailable

### Documentation

- README with architecture diagram and quick start
- Production deployment guide (secrets, backups, monitoring)
- API reference with all endpoints
- WebSocket protocol specification
- API error code reference
- Integration testing checklist
- Pre-launch security & performance checklist
- Contributing guide
