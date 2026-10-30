import logging
from uuid import uuid4

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response

logger = logging.getLogger(__name__)


class TraceMiddleware:
    """Generate a trusted trace per request and sanitize unhandled API failures."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = str(uuid4())
        scope.setdefault("state", {})["trace_id"] = trace_id
        started = False

        async def send_with_trace(message: Message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-trace-id"]
                message["headers"] = headers + [(b"x-trace-id", trace_id.encode("ascii"))]
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        except Exception as exc:
            # Do not log exception messages, request bodies, headers, or query strings.
            logger.error("request_failed trace_id=%s exception_type=%s", trace_id, type(exc).__name__)
            if started:
                raise
            response = error_response(
                Request(scope), 500, "internal_error", "An unexpected error occurred"
            )
            await response(scope, receive, send_with_trace)
