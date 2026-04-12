# API Reference

## Interactive Documentation

The API ships with auto-generated interactive docs:

- **Swagger UI**: `http://localhost:8000/docs` (dev) or `https://<domain>/api/docs` (prod)
- **ReDoc**: `http://localhost:8000/redoc`

All endpoints, request/response schemas, and authentication requirements are documented there.

## Base URL

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:8000` |
| Production | `https://<domain>/api` (proxied through nginx) |

## Authentication

Most endpoints require a Bearer token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Auth flow

1. **Register**: `POST /api/auth/register` &rarr; returns user + owner
2. **Login**: `POST /api/auth/login` &rarr; returns `access_token` + `refresh_token`
3. **Refresh**: `POST /api/auth/refresh` with refresh token &rarr; new access token
4. **2FA** (optional): `POST /api/security/2fa/verify` after login if TOTP is enabled

Access tokens expire after 60 minutes (configurable). Refresh tokens last 30 days.

## REST API Endpoints

### Auth & Security

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/register` | Register a new user |
| `POST` | `/api/auth/login` | Login, get tokens |
| `POST` | `/api/auth/refresh` | Refresh access token |
| `POST` | `/api/security/2fa/setup` | Enable TOTP 2FA |
| `POST` | `/api/security/2fa/verify` | Verify TOTP code |
| `POST` | `/api/security/export` | Request data export |
| `DELETE` | `/api/security/delete-account` | Delete account |

### Chat & Conversations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/chat/threads` | List conversation threads |
| `GET` | `/api/chat/threads/{id}/messages` | Get messages in a thread |
| `POST` | `/api/chat/threads` | Create a new thread |
| `DELETE` | `/api/chat/threads/{id}` | Delete a thread |

Real-time chat is handled via WebSocket &mdash; see [WebSocket Protocol](websocket-protocol.md).

### Knowledge

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/knowledge/ingest` | Upload and ingest a document |
| `GET` | `/api/knowledge/entries` | List knowledge entries |
| `DELETE` | `/api/knowledge/entries/{id}` | Remove a knowledge entry |
| `POST` | `/api/knowledge/search` | Search knowledge base |

### Voice & Face Verification

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/verify/voice/enroll` | Submit voice sample for enrollment |
| `POST` | `/api/verify/voice/check` | Verify a voice sample |
| `GET` | `/api/verify/voice/status` | Get enrollment status |
| `POST` | `/api/verify/face/enroll` | Submit face image for enrollment |
| `POST` | `/api/verify/face/check` | Verify a face image |
| `GET` | `/api/verify/face/status` | Get enrollment status |

### Personality & Learning

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/personality/profile` | Get personality profile |
| `GET` | `/api/personality/emotions` | Get emotion history |
| `POST` | `/api/learning/trigger` | Trigger self-learning cycle |
| `GET` | `/api/learning/status` | Get learning status |

### Fine-tuning

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/finetune/export` | Export training data |
| `POST` | `/api/finetune/trigger` | Start fine-tuning job |
| `GET` | `/api/finetune/status` | Get fine-tuning status |
| `GET` | `/api/finetune/versions` | List model versions |

### External LLM

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/external/providers` | List configured providers |
| `POST` | `/api/external/query` | Query an external LLM |
| `GET` | `/api/external/budget` | Get budget status |

### Web Browsing

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/browse/fetch` | Fetch and extract a URL |
| `POST` | `/api/browse/search` | Web search |
| `POST` | `/api/browse/monitors` | Create a page monitor |
| `GET` | `/api/browse/monitors` | List active monitors |
| `DELETE` | `/api/browse/monitors/{id}` | Remove a monitor |

### Family Access

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/access/invite` | Create family invite |
| `POST` | `/api/access/join` | Join via invite code |
| `GET` | `/api/access/members` | List family members |
| `PUT` | `/api/access/rules/{member_id}` | Update member rules |
| `DELETE` | `/api/access/members/{member_id}` | Remove a member |
| `POST` | `/api/access/qr` | Generate QR invite code |

### Billing

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/billing/status` | Get subscription status |
| `POST` | `/api/billing/subscribe` | Create Stripe checkout |
| `POST` | `/api/billing/webhook` | Stripe webhook receiver |
| `POST` | `/api/billing/cancel` | Cancel subscription |

### Multi-Instance Sync

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/instances/register` | Register this instance |
| `GET` | `/api/instances` | List known instances |
| `POST` | `/api/sync/push` | Push state to peers |
| `POST` | `/api/sync/pull` | Pull state from peers |
| `POST` | `/api/sync/resolve` | Resolve sync conflicts |

### Model Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/model/status` | Get active model info |
| `POST` | `/api/model/switch` | Switch active model |

### Search

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/search` | Full-text + semantic search |

### Push Notifications

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/push/subscribe` | Register push subscription |
| `POST` | `/api/push/unsubscribe` | Remove push subscription |
| `GET` | `/api/push/vapid-public-key` | Get VAPID public key |
| `POST` | `/api/push/test` | Send test notification |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | API health check |
| `GET` | `/api/health/detailed` | Detailed health (DB, Redis, AI) |

## WebSocket Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/ws/chat/{owner_id}` | Streaming text chat with RAG |
| `/ws/voice/{owner_id}` | Full-duplex voice call (STT + LLM + TTS) |
| `/ws/video/{owner_id}` | Video call with audio + face verification |
| `/ws/family/chat/{owner_id}` | Family member chat channel |

All WebSocket endpoints require JWT authentication. See [WebSocket Protocol](websocket-protocol.md) for the full message format.

## Rate Limiting

Requests are rate-limited per IP with category-specific budgets:

| Category | Paths | Default limit |
|----------|-------|--------------|
| Auth | `/api/auth/*`, `/api/security/2fa/*` | 10/min |
| Chat | `/api/chat/*`, `/ws/*` | 60/min |
| Upload | `/api/knowledge/*`, `/api/voice/*`, `/api/verify/*` | 20/min |
| Search | `/api/search/*`, `/api/browse/*` | 60/min |
| Billing | `/api/billing/*`, `/api/external/*` | 20/min |
| General | All other `/api/*` | 100/min |

When rate-limited, the server returns `429 Too Many Requests` with a `Retry-After: 60` header.

## Error Handling

All errors follow a consistent envelope. See [API Errors](api-errors.md) for the full error code reference.

```json
{
  "error": {
    "code": "AUTH_FAILED",
    "message": "Authentication failed.",
    "details": {}
  }
}
```

Every response includes an `X-Request-Id` header for log correlation.
