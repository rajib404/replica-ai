# API Error Reference

Every error response from the Replica AI API follows the same envelope:

```json
{
  "error": {
    "code": "AUTH_FAILED",
    "message": "Authentication failed.",
    "details": {}
  }
}
```

Responses also include an `X-Request-Id` header so clients can correlate
a failure with server logs when contacting support.

## Error codes

| Code | HTTP | When it's raised | Client action |
|------|------|------------------|---------------|
| `AUTH_FAILED` | 401 | Missing, invalid or expired access token | Refresh token via `/api/auth/refresh` and retry |
| `FORBIDDEN` | 403 | Authenticated user can't perform this action | Show a permission-denied message |
| `NOT_FOUND` | 404 | Resource doesn't exist | Show a friendly "not found" state |
| `METHOD_NOT_ALLOWED` | 405 | Wrong HTTP verb | Bug — fix the client |
| `CONFLICT` | 409 | Resource already exists or state conflict | Show server message |
| `VALIDATION_ERROR` | 400 / 422 | Request failed schema validation. `details.fields` contains the offending fields | Highlight the fields |
| `PAYLOAD_TOO_LARGE` | 413 | Upload exceeds the per-category limit. `details.max_bytes` carries the cap | Ask user for a smaller file |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | File extension isn't in the allowed list | Show allowed formats |
| `RATE_LIMIT_EXCEEDED` | 429 | Caller exceeded per-IP rate limit. `Retry-After` header tells you when to retry | Back off and retry |
| `INSUFFICIENT_FUNDS` | 402 | External LLM monthly budget exhausted | Offer fallback to local model |
| `SYNC_CONFLICT` | 409 | Replica sync detected divergent state between instances | Surface conflict resolution UI |
| `MODEL_UNAVAILABLE` | 503 | Local LLM or external provider can't be reached after retries | Show "temporarily unavailable, please try again" |
| `UPSTREAM_ERROR` | 502 | A downstream service (ai service, external LLM) returned an error | Retry or show error to user |
| `STORAGE_ERROR` | 500 | File storage operation failed | Retry or report to support |
| `DATABASE_ERROR` | 500 | Unrecoverable database error (after retries) | Retry or report to support |
| `INTERNAL_ERROR` | 500 | Uncaught exception — the last line of defense | Include `X-Request-Id` in bug report |

## Retryable errors

Clients can retry these error codes with exponential backoff:

- `MODEL_UNAVAILABLE` (503)
- `UPSTREAM_ERROR` (502)
- `RATE_LIMIT_EXCEEDED` (429) — honour the `Retry-After` header
- `DATABASE_ERROR` (500) — retry up to twice

All other error codes should *not* be retried automatically; they
indicate a problem with the request that won't be fixed by retrying.

## Graceful degradation responses

Some responses may return successfully (2xx) but carry a `degraded: true`
flag and a `warning` field. These indicate that a non-critical dependency
was unavailable and the response was built from a fallback path:

```json
{
  "response": "...",
  "sources": [],
  "degraded": true,
  "warning": "Knowledge search is temporarily unavailable..."
}
```

Degraded responses are not errors — don't treat them as failures. Do
surface the warning to the user so they know they may be getting
reduced-quality answers.

## Request correlation

Every response carries an `X-Request-Id` header. Include this value in
bug reports — it lets the server-side team find the exact log line for
your failed request.

You can also provide your own request id by sending an `X-Request-Id`
request header; the server will echo it back in the response.
