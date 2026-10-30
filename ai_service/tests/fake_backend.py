"""An in-process fake of the backend REST API (README §4 contract), served
through httpx.MockTransport. It wraps the mock adapter's data in the agreed
{status, data, trace_id} envelopes and enforces bearer auth, so the real
HttpLibraryToolAdapter can be contract-tested without a network."""
import json
import re
import uuid
from datetime import datetime

import httpx

from app.adapters.errors import ToolError
from app.adapters.mock_adapter import MockLibraryToolAdapter
from app.auth.context import UserContext
from app.auth.identity import MockIdentityAdapter
from app.schemas.library import User
from tests.conftest import FIXTURES

INDEXER_TOKEN = "backend-indexer-token"
# Canonical ToolError code -> (backend error code, HTTP status), per the backend handoff
_BACKEND_ERRORS = {
    "not_found": ("not_found", 404), "permission_denied": ("forbidden", 403),
    "unauthorized": ("unauthorized", 401), "conflict": ("duplicate_reservation", 409),
    "not_renewable": ("renewal_not_allowed", 409), "invalid_argument": ("validation_error", 422),
    "backend_timeout": ("internal_error", 500), "backend_error": ("internal_error", 500),
}


class FakeBackend:
    def __init__(self):
        self.lib = MockLibraryToolAdapter(FIXTURES)
        self.identity = MockIdentityAdapter(FIXTURES)
        self.requests: list[httpx.Request] = []
        # path regex -> "timeout" | "500" | "html" | "malformed" | "down" | "busy"
        self.fail: dict[str, str] = {}
        self.busy_responses = 0  # how many 409 database_busy replies "busy" mode sends before succeeding

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def ok(data, status=200):
        body = {"status": "success", "data": data, "trace_id": uuid.uuid4().hex}
        return httpx.Response(status, json=json.loads(json.dumps(body, default=str)))

    @staticmethod
    def err(code, message, status=None):
        code, default_status = _BACKEND_ERRORS.get(code, (code, 400))
        body = {"status": "error", "error": {"code": code, "message": message}, "trace_id": uuid.uuid4().hex}
        return httpx.Response(status or default_status, json=body)

    async def _user(self, request) -> UserContext | None:
        auth = request.headers.get("Authorization", "")
        if not auth:
            return None
        token = auth.removeprefix("Bearer ").strip()
        if token == INDEXER_TOKEN:
            return UserContext("svc-ai-indexer", "AI Indexer", "librarian", token)
        return await self.identity.authenticate(token)  # raises ToolError(unauthorized)

    # ------------------------------------------------------------------ routing

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api/v1")
        for pattern, mode in self.fail.items():
            if re.fullmatch(pattern, path):
                if mode == "timeout":
                    raise httpx.ReadTimeout("timed out", request=request)
                if mode == "down":
                    raise httpx.ConnectError("connection refused", request=request)
                if mode == "500":
                    return self.err("internal", "DB connection pool exhausted at db-7.internal", 500)
                if mode == "html":
                    return httpx.Response(502, text="<html>Bad Gateway</html>")
                if mode == "malformed":
                    return self.ok({"unexpected": True})
                if mode == "busy" and self.busy_responses > 0:
                    self.busy_responses -= 1
                    return self.err("database_busy", "Database is busy, retry with the same key", 409)
        try:
            return await self._route(request, path)
        except ToolError as e:
            return self.err(e.code, e.message)

    async def _route(self, request: httpx.Request, path: str) -> httpx.Response:
        m, q = request.method, request.url.params
        user = await self._user(request)

        if m == "GET" and path == "/health":
            return self.ok({"status": "ok"})
        if m == "GET" and path == "/auth/me":
            if user is None:
                return self.err("unauthorized", "Missing token")
            u = self.lib.users[user.user_id]
            return self.ok({"user_id": u.user_id, "name": u.name, "email": u.email, "role": u.role})
        if path == "/me/profile":  # contract: courses[] and interests[] only
            p = await self.lib.get_profile(user)
            return self.ok({"courses": p.courses, "interests": p.interests})
        if m == "GET" and path == "/resources":
            since = q.get("updated_since")
            res = await self.lib.search_resources(
                user, q.get("query", ""), limit=int(q.get("limit", 20)), offset=int(q.get("offset", 0)),
                type=q.get("type"), level=q.get("level"),
                updated_since=datetime.fromisoformat(since) if since else None)
            return self.ok(res.model_dump(mode="json"))
        if mt := re.fullmatch(r"/resources/([^/]+)", path):
            return self.ok((await self.lib.get_resource(user, mt[1])).model_dump(mode="json"))
        if mt := re.fullmatch(r"/resources/([^/]+)/availability", path):
            return self.ok((await self.lib.get_availability(user, mt[1])).model_dump(mode="json"))
        if mt := re.fullmatch(r"/resources/([^/]+)/content", path):
            return self.ok((await self.lib.get_resource_content(user, mt[1])).model_dump(mode="json"))
        if path == "/me/loans":
            return self.ok({"items": [l.model_dump(mode="json") for l in await self.lib.get_my_loans(user)]})
        if path == "/me/reservations":
            return self.ok({"items": [r.model_dump(mode="json") for r in await self.lib.get_my_reservations(user)]})
        if m == "POST" and path == "/reservations":
            key = request.headers.get("Idempotency-Key")
            if not key:
                return self.err("invalid_argument", "Idempotency-Key header required")
            body = json.loads(request.content)
            res = await self.lib.create_reservation(user, body["resource_id"], key)
            return self.ok(res.model_dump(mode="json"), status=201)
        if m == "POST" and (mt := re.fullmatch(r"/loans/([^/]+)/renew", path)):
            key = request.headers.get("Idempotency-Key")
            if not key:
                return self.err("invalid_argument", "Idempotency-Key header required")
            return self.ok((await self.lib.renew_loan(user, mt[1], key)).model_dump(mode="json"))
        if path == "/analytics/summary":
            return self.ok((await self.lib.get_analytics_summary(user)).model_dump(mode="json"))
        return self.err("not_found", f"No route {m} {path}")


__all__ = ["FakeBackend", "INDEXER_TOKEN", "User"]
