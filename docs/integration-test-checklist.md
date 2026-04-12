# Integration Test Checklist

Manual integration testing guide for Replica AI v1.0.0. Work through each step sequentially &mdash; later steps depend on state from earlier ones.

---

## 1. User Registration & Login

**Preconditions:** Services running (`make dev` or production stack), clean database or known test state.

- [ ] `POST /api/auth/register` with email + password &rarr; 201, returns user object with `owner_id`
- [ ] `POST /api/auth/login` with same credentials &rarr; 200, returns `access_token` + `refresh_token`
- [ ] `POST /api/auth/login` with wrong password &rarr; 401
- [ ] `POST /api/auth/refresh` with refresh token &rarr; 200, new access token
- [ ] Use expired access token &rarr; 401 `AUTH_FAILED`
- [ ] Verify rate limiting: send 11 login requests in under a minute &rarr; 429 on the 11th

**Verification:**
```bash
curl -s http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","password":"Test1234!"}' | jq .
```

---

## 2. 2FA Setup & Verification

**Preconditions:** Logged in with valid access token.

- [ ] `POST /api/security/2fa/setup` &rarr; returns TOTP secret + QR URI
- [ ] Scan QR code in authenticator app (or use `pyotp` to generate code)
- [ ] `POST /api/security/2fa/verify` with valid TOTP code &rarr; success
- [ ] `POST /api/security/2fa/verify` with invalid code &rarr; failure
- [ ] Subsequent logins require 2FA step

---

## 3. Text Chat (WebSocket)

**Preconditions:** Valid access token, `owner_id` from registration.

- [ ] Connect to `ws://localhost:8000/ws/chat/{owner_id}?token={access_token}`
- [ ] Receive `auth_ok` message
- [ ] Send `{"type":"message","text":"Hello, who are you?"}`
- [ ] Receive streaming `response_token` messages followed by `response_done`
- [ ] `response_done` includes `thread_id`, `message_id`, `sources`
- [ ] Send follow-up message in same thread &rarr; context is maintained
- [ ] Connect with invalid token &rarr; close code `4001`
- [ ] Connect with expired token &rarr; close code `4004`

**Degraded mode test:**
- [ ] Stop Qdrant (`docker stop` the container)
- [ ] Send a chat message &rarr; response still works, `degraded: true` in `response_done`
- [ ] Restart Qdrant &rarr; subsequent messages include RAG sources again

---

## 4. Knowledge Ingestion & RAG

**Preconditions:** Authenticated, chat working.

- [ ] `POST /api/knowledge/ingest` with a PDF file &rarr; 200, returns entry ID
- [ ] `POST /api/knowledge/ingest` with a .txt file &rarr; 200
- [ ] `GET /api/knowledge/entries` &rarr; lists ingested entries
- [ ] Chat about the ingested content &rarr; `sources` in response reference the documents
- [ ] `DELETE /api/knowledge/entries/{id}` &rarr; 200, entry removed
- [ ] Upload a .exe file &rarr; 415 `UNSUPPORTED_MEDIA_TYPE`
- [ ] Upload a .txt file renamed to .pdf (MIME mismatch) &rarr; 415

---

## 5. Voice Enrollment & Voice Chat

**Preconditions:** Authenticated, microphone available.

- [ ] `POST /api/verify/voice/enroll` &times; 3 with voice samples (&ge; 10s each) &rarr; enrollment complete
- [ ] `GET /api/verify/voice/status` &rarr; `enrolled: true`
- [ ] Connect to `ws://localhost:8000/ws/voice/{owner_id}?token={token}`
- [ ] Receive `auth_ok`
- [ ] Send audio frames (PCM16, 16kHz) + `end_utterance`
- [ ] Receive `transcript` (STT), `response_text` (LLM), `audio_out` + binary TTS audio
- [ ] Verify `status` messages cycle: `listening` &rarr; `thinking` &rarr; `speaking`
- [ ] Send `cancel` during TTS playback &rarr; playback stops

---

## 6. Face Enrollment & Video Call

**Preconditions:** Authenticated, camera available.

- [ ] `POST /api/verify/face/enroll` &times; 5 with face images &rarr; enrollment complete
- [ ] `GET /api/verify/face/status` &rarr; `enrolled: true`
- [ ] Connect to `ws://localhost:8000/ws/video/{owner_id}?token={token}`
- [ ] Send audio frames (same as voice chat)
- [ ] Send `face_frame` + JPEG binary every ~5s
- [ ] Receive `face_result` with `verified: true` and confidence score
- [ ] Send someone else's face &rarr; `verified: false`

---

## 7. Family Access

**Preconditions:** Authenticated as the owner.

- [ ] `POST /api/access/invite` &rarr; returns invite code
- [ ] `POST /api/access/qr` &rarr; returns QR code image
- [ ] In a separate session, `POST /api/access/join` with invite code &rarr; success
- [ ] `GET /api/access/members` as owner &rarr; lists the new member
- [ ] `PUT /api/access/rules/{member_id}` &rarr; set topic restrictions
- [ ] Connect as family member to `ws://localhost:8000/ws/family/chat/{owner_id}`
- [ ] Send a message &rarr; response respects configured rules
- [ ] Send a message on a restricted topic &rarr; filtered/blocked
- [ ] `DELETE /api/access/members/{member_id}` as owner &rarr; member removed

---

## 8. External LLM & Budget

**Preconditions:** External LLM provider configured in env (e.g., OpenAI API key).

- [ ] `GET /api/external/providers` &rarr; lists configured providers
- [ ] `POST /api/external/query` with a prompt &rarr; response from external LLM
- [ ] `GET /api/external/budget` &rarr; shows spending and remaining budget
- [ ] Exhaust budget &rarr; `402 INSUFFICIENT_FUNDS`

---

## 9. Web Browsing

**Preconditions:** Authenticated, API service has outbound internet access.

- [ ] `POST /api/browse/fetch` with a URL &rarr; extracted page content
- [ ] `POST /api/browse/search` with a query &rarr; search results
- [ ] `POST /api/browse/monitors` to watch a URL &rarr; monitor created
- [ ] `GET /api/browse/monitors` &rarr; lists the monitor
- [ ] Wait for check interval &rarr; monitor detects changes (or no change)
- [ ] `DELETE /api/browse/monitors/{id}` &rarr; monitor removed

---

## 10. Billing (Stripe Test Mode)

**Preconditions:** Stripe test keys configured, `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` set.

- [ ] `POST /api/billing/subscribe` &rarr; returns Stripe checkout URL
- [ ] Complete checkout with Stripe test card `4242 4242 4242 4242`
- [ ] Stripe webhook fires &rarr; `POST /api/billing/webhook` processes it
- [ ] `GET /api/billing/status` &rarr; `active` subscription
- [ ] `POST /api/billing/cancel` &rarr; subscription cancelled
- [ ] Verify survival mode activates after grace period expires

---

## 11. Multi-Instance Sync

**Preconditions:** Two instances running (or simulate with different instance IDs).

- [ ] `POST /api/instances/register` on instance A &rarr; registered
- [ ] `POST /api/instances/register` on instance B &rarr; registered
- [ ] `GET /api/instances` &rarr; both instances listed
- [ ] Create knowledge on instance A, `POST /api/sync/push` &rarr; synced
- [ ] `POST /api/sync/pull` on instance B &rarr; knowledge appears
- [ ] Create conflicting state &rarr; `POST /api/sync/resolve` handles it

---

## 12. Security Audit Checks

- [ ] All API responses include `X-Request-Id` header
- [ ] All API responses include security headers (HSTS, CSP, X-Frame-Options, etc.)
- [ ] Upload a file with mismatched extension/content &rarr; 415 MIME validation error
- [ ] Rapid-fire requests to different categories &rarr; each has independent rate limit
- [ ] Access `/api/security/export` &rarr; data export generated
- [ ] Access `/api/security/delete-account` with confirmation phrase &rarr; account deleted
- [ ] Verify audit log entries exist for login, 2FA, export, deletion events

---

## 13. Health & Monitoring

- [ ] `GET /health` &rarr; 200
- [ ] `GET /api/health/detailed` &rarr; shows status of DB, Redis, AI service
- [ ] Stop Redis &rarr; health shows degraded, chat still works (`cache_optional: true`)
- [ ] Stop AI service &rarr; health shows unhealthy, chat returns 503
- [ ] Restart all services &rarr; health returns to normal

---

## Post-Test Cleanup

```bash
# If using dev environment, reset to clean state:
make docker-down
docker volume prune -f
make docker-up
make db-migrate
```
