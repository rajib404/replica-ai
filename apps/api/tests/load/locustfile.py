"""
Locust load tests for the Replica AI FastAPI backend.

Run a smoke test against a local API:

    cd apps/api
    pip install -e ".[load]"
    locust -f tests/load/locustfile.py --host http://localhost:8000

Or headless with a fixed user count:

    locust -f tests/load/locustfile.py \
        --host http://localhost:8000 \
        --users 50 --spawn-rate 5 --run-time 2m --headless

Three user classes are defined and weighted:

* ``OwnerChatUser`` (weight 5) — Authenticates once via /api/auth/setup, then
  loops through chat + knowledge + thread-list operations. This is the most
  representative real-world traffic pattern.
* ``KnowledgeIngestionUser`` (weight 2) — Hammers the text-ingest endpoint with
  short documents. Useful for measuring DB write throughput and AI service
  back-pressure.
* ``HealthCheckUser`` (weight 1) — Pings the public health endpoints. Acts as
  the baseline for "is the service even alive under load" measurements.

The chat and knowledge users assume the AI service (apps/ai on :8100) is
running and reachable from the API. For pure load profiling without a real
LLM you can stub the AI client by setting ``AI_SERVICE_URL`` to a mock server
or running apps/ai with the ``MOCK_LLM=1`` environment variable.
"""

from __future__ import annotations

import random
import uuid

from locust import HttpUser, between, events, task
from locust.exception import StopUser


# ─── Sample data ─────────────────────────────────────────

# Realistic-ish chat prompts. Kept short so test runs aren't dominated by
# LLM latency — for stress testing the API layer rather than the model.
CHAT_PROMPTS: list[str] = [
    "Tell me about your day.",
    "What did you do last weekend?",
    "Do you remember my birthday?",
    "What's your favorite recipe?",
    "How are you feeling today?",
    "Can you remind me what we discussed yesterday?",
    "Tell me a story about your childhood.",
    "What advice would you give a young person starting out?",
    "What's something you wish you'd done differently?",
    "Who is your best friend?",
]

# Short knowledge snippets for the text-ingest endpoint. Each one is treated
# as a separate "memory" by the AI service.
KNOWLEDGE_SNIPPETS: list[str] = [
    "I grew up in a small town near the coast. Every summer we'd go to the beach.",
    "My grandmother taught me how to make her famous apple pie when I was twelve.",
    "I started my first job at the bakery on Main Street in 1972.",
    "We adopted our dog, Rosie, from the shelter on a rainy Tuesday in March.",
    "The first time I traveled abroad was to Paris in 1985. I still remember the smell of the bakery near our hotel.",
    "My favorite book is To Kill a Mockingbird. I've read it five times.",
    "I met my spouse at a friend's wedding. We danced to a Stevie Wonder song.",
    "My proudest moment was watching my daughter graduate from college.",
]

LANGUAGES: list[str] = ["en", "es", "fr", "it"]


# ─── Helpers ────────────────────────────────────────────


def _unique_email() -> str:
    """Return a globally-unique synthetic email so /api/auth/setup never collides."""
    return f"loadtest-{uuid.uuid4().hex[:12]}@example.com"


def _setup_payload() -> dict:
    """Build a fresh /api/auth/setup payload."""
    return {
        "name": f"Load Test User {uuid.uuid4().hex[:6]}",
        "email": _unique_email(),
        "preferred_language": random.choice(LANGUAGES),
        "secret_word": "loadtestsecret",
    }


# ─── User: Authenticated chat owner ─────────────────────


class OwnerChatUser(HttpUser):
    """Simulates a real owner using the app: chat, ingest knowledge, browse threads.

    Each virtual user calls /api/auth/setup once at start to provision an
    isolated owner record + JWT, then keeps that token for the rest of its
    session. Mimics a single human keeping the app open and interacting at
    a leisurely pace (1-4 seconds between actions).
    """

    wait_time = between(1, 4)
    weight = 5

    def on_start(self) -> None:
        """Provision an owner and grab a bearer token."""
        response = self.client.post(
            "/api/auth/setup",
            json=_setup_payload(),
            name="POST /api/auth/setup",
        )
        if response.status_code != 201:
            # Without auth this user can't do anything; bail out gracefully.
            response.failure(f"Setup failed: {response.status_code} {response.text[:200]}")
            raise StopUser()

        data = response.json()
        self.owner_id: str = data["owner_id"]
        self.access_token: str = data["tokens"]["access_token"]
        self.refresh_token: str = data["tokens"]["refresh_token"]
        self.client.headers["Authorization"] = f"Bearer {self.access_token}"
        self.thread_id: str | None = None

    @task(10)
    def send_chat_message(self) -> None:
        payload: dict = {"message": random.choice(CHAT_PROMPTS)}
        if self.thread_id:
            payload["thread_id"] = self.thread_id

        with self.client.post(
            "/api/chat/message",
            json=payload,
            name="POST /api/chat/message",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"chat failed: {response.status_code}")
                return
            try:
                data = response.json()
            except ValueError:
                response.failure("chat response was not JSON")
                return
            # Capture the thread on the first successful exchange so the rest
            # of this user's messages thread together.
            if self.thread_id is None:
                self.thread_id = data.get("thread_id")

    @task(3)
    def ingest_knowledge_text(self) -> None:
        self.client.post(
            "/api/knowledge/text",
            json={
                "text": random.choice(KNOWLEDGE_SNIPPETS),
                "language": random.choice(LANGUAGES),
            },
            name="POST /api/knowledge/text",
        )

    @task(2)
    def list_threads(self) -> None:
        self.client.get("/api/chat/threads", name="GET /api/chat/threads")

    @task(2)
    def list_knowledge(self) -> None:
        self.client.get("/api/knowledge/entries", name="GET /api/knowledge/entries")

    @task(1)
    def fetch_thread_messages(self) -> None:
        if not self.thread_id:
            return
        self.client.get(
            f"/api/chat/threads/{self.thread_id}/messages",
            name="GET /api/chat/threads/{id}/messages",
        )

    @task(1)
    def refresh_token(self) -> None:
        with self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": self.refresh_token},
            name="POST /api/auth/refresh",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"refresh failed: {response.status_code}")
                return
            data = response.json()
            tokens = data.get("tokens", {})
            new_access = tokens.get("access_token")
            new_refresh = tokens.get("refresh_token")
            if new_access:
                self.access_token = new_access
                self.client.headers["Authorization"] = f"Bearer {self.access_token}"
            if new_refresh:
                self.refresh_token = new_refresh


# ─── User: Knowledge bulk ingest ────────────────────────


class KnowledgeIngestionUser(HttpUser):
    """Hammers /api/knowledge/text to measure ingest throughput.

    Each user authenticates once and then ingests text snippets back-to-back
    with very small think-time. Use this class to find the point at which
    the AI service or the DB starts queueing.
    """

    wait_time = between(0.2, 1.0)
    weight = 2

    def on_start(self) -> None:
        response = self.client.post(
            "/api/auth/setup",
            json=_setup_payload(),
            name="POST /api/auth/setup",
        )
        if response.status_code != 201:
            response.failure(f"Setup failed: {response.status_code}")
            raise StopUser()

        data = response.json()
        self.client.headers["Authorization"] = f"Bearer {data['tokens']['access_token']}"

    @task
    def ingest_text(self) -> None:
        self.client.post(
            "/api/knowledge/text",
            json={
                "text": random.choice(KNOWLEDGE_SNIPPETS),
                "language": "en",
            },
            name="POST /api/knowledge/text",
        )


# ─── User: Public health checks ─────────────────────────


class HealthCheckUser(HttpUser):
    """Background traffic against the public health endpoints.

    Used to:
      * confirm liveness while the heavier user classes apply pressure
      * measure how much p99 latency drift the API picks up under load
    """

    wait_time = between(2, 5)
    weight = 1

    @task(3)
    def basic_health(self) -> None:
        self.client.get("/api/health", name="GET /api/health")

    @task(1)
    def detailed_health(self) -> None:
        self.client.get("/api/health/detailed", name="GET /api/health/detailed")


# ─── Hooks ──────────────────────────────────────────────


@events.test_start.add_listener
def _on_test_start(environment, **_kwargs) -> None:
    """Print the target host once at start so failed runs are easy to triage."""
    host = getattr(environment, "host", None) or "<no host>"
    print(f"[locust] starting load test against {host}")


@events.test_stop.add_listener
def _on_test_stop(environment, **_kwargs) -> None:
    stats = environment.stats.total
    print(
        f"[locust] finished: {stats.num_requests} requests, "
        f"{stats.num_failures} failures, "
        f"median={stats.median_response_time}ms, "
        f"p95={stats.get_response_time_percentile(0.95)}ms"
    )
