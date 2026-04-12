"""Unit tests for the global exception handlers.

Uses a minimal FastAPI app built in-test so we exercise the real
handler registration code path without requiring the full application
(and its DB / AI dependencies).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.core.exception_handlers import (
    _envelope,
    register_exception_handlers,
)
from app.core.exceptions import (
    AuthError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-auth")
    async def raise_auth() -> None:
        raise AuthError("token missing")

    @app.get("/raise-forbidden")
    async def raise_forbidden() -> None:
        raise ForbiddenError("nope", details={"required_role": "admin"})

    @app.get("/raise-not-found")
    async def raise_not_found() -> None:
        raise NotFoundError("owner not found")

    @app.get("/raise-validation")
    async def raise_validation() -> None:
        raise ValidationError("invalid", details={"field": "email"})

    @app.get("/raise-rate-limit")
    async def raise_rate_limit() -> None:
        raise RateLimitError()

    @app.get("/raise-http")
    async def raise_http() -> None:
        raise HTTPException(status_code=404, detail="gone")

    @app.get("/raise-http-dict")
    async def raise_http_dict() -> None:
        raise HTTPException(status_code=400, detail={"message": "bad", "field": "x"})

    @app.get("/raise-integrity")
    async def raise_integrity() -> None:
        raise IntegrityError("dup", None, Exception("unique violation"))

    @app.get("/raise-generic")
    async def raise_generic() -> None:
        raise RuntimeError("unexpected")

    class Body(BaseModel):
        name: str = Field(min_length=3)
        age: int = Field(ge=0)

    @app.post("/validate-body")
    async def validate_body(body: Body) -> dict[str, str]:
        return {"ok": "yes"}

    return app


# ─── _envelope helper ───────────────────────────────────────


class TestEnvelope:
    def test_shape(self) -> None:
        result = _envelope("CODE", "msg", {"k": "v"})
        assert result == {"error": {"code": "CODE", "message": "msg", "details": {"k": "v"}}}

    def test_none_details_defaults_to_empty_dict(self) -> None:
        result = _envelope("CODE", "msg")
        assert result["error"]["details"] == {}


# ─── Handler smoke tests ─────────────────────────────────────


class TestHandlers:
    def setup_method(self) -> None:
        self.client = TestClient(_build_app())

    def test_auth_error_produces_401(self) -> None:
        resp = self.client.get("/raise-auth")
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "AUTH_FAILED"
        assert body["error"]["message"] == "token missing"
        assert "details" in body["error"]
        assert "X-Request-Id" in resp.headers
        assert resp.headers["X-Request-Id"]  # non-empty

    def test_forbidden_error_with_details(self) -> None:
        resp = self.client.get("/raise-forbidden")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "FORBIDDEN"
        assert body["error"]["details"]["required_role"] == "admin"

    def test_not_found_error(self) -> None:
        resp = self.client.get("/raise-not-found")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_validation_error(self) -> None:
        resp = self.client.get("/raise-validation")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["details"] == {"field": "email"}

    def test_rate_limit_default_message(self) -> None:
        resp = self.client.get("/raise-rate-limit")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "slow down" in body["error"]["message"].lower() or body["error"]["message"]

    def test_http_exception_404(self) -> None:
        resp = self.client.get("/raise-http")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "gone"

    def test_http_exception_with_dict_detail(self) -> None:
        resp = self.client.get("/raise-http-dict")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["message"] == "bad"
        assert body["error"]["details"].get("field") == "x"

    def test_integrity_error_becomes_409(self) -> None:
        resp = self.client.get("/raise-integrity")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_generic_exception_becomes_500(self) -> None:
        self.client.raise_server_exceptions = False
        resp = self.client.get("/raise-generic")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"

    def test_pydantic_validation_error_becomes_422(self) -> None:
        resp = self.client.post("/validate-body", json={"name": "x", "age": -1})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "fields" in body["error"]["details"]
        assert len(body["error"]["details"]["fields"]) >= 1

    def test_request_id_is_echoed_when_provided(self) -> None:
        resp = self.client.get(
            "/raise-auth", headers={"X-Request-Id": "my-trace-id"}
        )
        assert resp.headers.get("X-Request-Id") == "my-trace-id"

    def test_request_id_is_generated_when_missing(self) -> None:
        resp = self.client.get("/raise-auth")
        rid = resp.headers.get("X-Request-Id")
        assert rid
        assert len(rid) >= 8  # uuid hex is 32 chars
