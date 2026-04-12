# WebSocket Protocol

Replica AI uses WebSockets for streaming chat, voice, and video calls.
All WebSocket endpoints share the same authentication pattern and a
similar frame-based message format.

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/ws/chat/{owner_id}` | Streaming text chat with RAG |
| `/ws/voice/{owner_id}` | Full-duplex voice call (STT + LLM + TTS) |
| `/ws/video/{owner_id}` | Video call with audio + periodic face frames |
| `/ws/family/chat/{owner_id}` | Family-member chat channel |

## Authentication

Every WebSocket requires a valid access token (JWT). The server accepts
the token in one of two ways:

1. **Query parameter** (preferred for browsers):
   ```
   wss://api.example.com/ws/chat/<owner_id>?token=<access_token>
   ```
2. **First message after `accept()`**:
   ```json
   { "type": "auth", "token": "<access_token>" }
   ```

On success the server responds with:
```json
{ "type": "auth_ok", "owner_id": "<id>" }
```

On failure the server sends a `WSError` frame and closes with code:

| Close code | Meaning |
|------------|---------|
| `4001`     | Invalid or missing token |
| `4003`     | Authorization failed (owner mismatch, lockout) |
| `4004`     | Token expired — refresh and reconnect |
| `1011`     | Internal server error |

## Message envelope

All JSON messages (client → server and server → client) carry a `type`
field that determines the shape of the payload. Unknown types are
ignored by the server (and should be ignored by the client).

Binary frames (voice audio, face images) are sent as raw bytes
immediately following a JSON control frame that describes them:

```text
client → server: {"type":"audio","sample_rate":16000,"format":"pcm16"}
client → server: <raw pcm16 audio bytes>
```

## `/ws/chat/{owner_id}` — Text chat

### Client → Server

| Type | Fields | Notes |
|------|--------|-------|
| `auth` | `token` | Only if not supplied as query param |
| `message` | `text`, `thread_id?` | Sends a new chat message |
| `challenge_response` | `challenge_id`, `answer?`, `method?`, `value?` | Reply to an identity challenge |

### Server → Client

| Type | Fields | Notes |
|------|--------|-------|
| `auth_ok` | `owner_id` | Authentication succeeded |
| `response_token` | `token`, `message_id` | One token of a streaming response |
| `response_done` | `message_id`, `thread_id`, `sources`, `is_learning` | Final frame of a response |
| `learning` | – | Signals that the owner message was ingested as knowledge |
| `challenge` | `challenge_id`, `challenge_type`, `question`, `methods`, `timeout_seconds` | Identity guard is challenging the user |
| `challenge_result` | `passed`, `message` | Result of a challenge response |
| `lockout` | – | Session locked due to suspicious activity |
| `error` | `detail` | Recoverable error — client may retry |

### Degraded mode

If the vector database (Qdrant) is unavailable, the server still
processes messages but falls back to plain generation without RAG.
The `response_done` frame carries `degraded: true` and a `warning`
field the client should display to the user. The connection is not
closed — chat stays functional.

## `/ws/voice/{owner_id}` — Voice call

### Client → Server

| Type | Fields | Notes |
|------|--------|-------|
| `audio` | `sample_rate`, `format` | Followed by a binary PCM frame |
| `end_utterance` | – | Triggers STT finalisation + LLM response |
| `cancel` | – | Abort current TTS playback |

### Server → Client

| Type | Fields | Notes |
|------|--------|-------|
| `transcript` | `text`, `is_final` | STT output |
| `response_text` | `text` | LLM response text (for captioning) |
| `audio_out` | `sample_rate`, `format`, `bytes` | Control frame for binary TTS |
| `status` | `state` | `listening` / `thinking` / `speaking` |
| `done` | – | End of a turn |
| `error` | `code`, `detail` | Error frame |

Binary TTS frames follow the `audio_out` control frame directly.

## `/ws/video/{owner_id}` — Video call

Extends the voice protocol with face-verification frames:

### Additional client → server messages

| Type | Fields | Notes |
|------|--------|-------|
| `face_frame` | – | Followed by a binary JPEG snapshot (~every 5 s) |

### Additional server → client messages

| Type | Fields | Notes |
|------|--------|-------|
| `face_result` | `verified`, `confidence`, `message` | Result of face check |
| `video_status` | `face_verified`, `call_duration_sec` | Heartbeat with call telemetry |

## Error frames

All WebSocket errors use a unified shape:

```json
{ "type": "error", "code": "MODEL_UNAVAILABLE", "detail": "..." }
```

Error `code` values mirror the REST API error codes documented in
[`api-errors.md`](./api-errors.md).

## Reconnection

Clients should reconnect with exponential backoff (1s, 2s, 4s, 8s cap)
on any non-4xx close code. On a 4001/4003/4004 close, the client must
obtain a fresh token via `POST /api/auth/refresh` before reconnecting.

## Rate limits

WebSocket message rates are not limited per-message; instead the
server relies on natural backpressure from the LLM pipeline. Upstream
REST endpoints (auth, thread listing) are rate-limited as documented
in the OpenAPI spec.
