import logging

from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.database import Database
from app.services.audit import AuditService

logger = logging.getLogger(__name__)

# Use trusted route templates; never store raw paths, query strings, bodies, or headers.
ACTIONS = {
    ("POST", "/api/v1/auth/login"): "auth.login",
    ("GET", "/api/v1/auth/me"): "auth.me",
    ("GET", "/api/v1/me/profile"): "profile.read",
    ("GET", "/api/v1/resources"): "catalog.search",
    ("GET", "/api/v1/resources/{resource_id}"): "catalog.read",
    ("GET", "/api/v1/resources/{resource_id}/availability"): "catalog.availability",
    ("GET", "/api/v1/resources/{resource_id}/content"): "catalog.content",
    ("POST", "/api/v1/resources"): "catalog.create",
    ("PATCH", "/api/v1/resources/{resource_id}"): "catalog.update",
    ("GET", "/api/v1/me/loans"): "circulation.loans.read",
    ("GET", "/api/v1/me/reservations"): "circulation.reservations.read",
    ("POST", "/api/v1/reservations"): "circulation.reserve",
    ("POST", "/api/v1/loans/{loan_id}/renew"): "circulation.renew",
    ("GET", "/api/v1/analytics/summary"): "analytics.summary",
}


def outcome(status: int) -> str:
    if 200 <= status < 300:
        return "success"
    return {400: "bad_request", 401: "denied", 403: "denied", 404: "not_found",
            405: "method_not_allowed", 409: "conflict", 422: "validation_error"}.get(status, "failed")


class RequestAuditMiddleware:
    def __init__(self, app: ASGIApp, database: Database):
        self.app = app
        self.audit = AuditService(database)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/") or scope["path"] == "/api/v1/health":
            await self.app(scope, receive, send)
            return
        status = 500

        async def capture_status(message: Message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            # Run after route dependencies close their sessions, so this request's
            # identity/login reads cannot block its own SQLite audit writer.
            state = scope.get("state", {})
            trace_id = state.get("trace_id")
            if trace_id:
                route = scope.get("route")
                action = ACTIONS.get((scope["method"], getattr(route, "path", "")), "request.unknown")
                try:
                    await run_in_threadpool(self.audit.record_request, state.get("audit_user_id"),
                                            action, outcome(status), trace_id)
                except Exception as exc:
                    # The response may already be sent. Preserve it and emit a safe
                    # operational signal; existing atomic business audits still fail closed.
                    logger.error("audit_persistence_failed trace_id=%s exception_type=%s", trace_id, type(exc).__name__)
