"""Real backend adapter: calls the agreed REST API with httpx.

- Base URL from BACKEND_BASE_URL (+ /api/v1)
- Forwards the caller's own bearer token; never a token from the LLM
- Unwraps {status, data, trace_id} envelopes into canonical models
- Maps error envelopes / HTTP statuses / timeouts to ToolError codes
- Sends Idempotency-Key on reservation and renewal"""
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.adapters.base import LibraryToolAdapter
from app.adapters.errors import ToolError
from app.auth.context import UserContext
from app.schemas.library import (
    AnalyticsSummary,
    Availability,
    Loan,
    Reservation,
    Resource,
    ResourceContent,
    SearchResult,
    User,
)

logger = logging.getLogger("smartlibrary.http_adapter")

_KNOWN_CODES = {
    ToolError.NOT_FOUND, ToolError.PERMISSION_DENIED, ToolError.UNAUTHORIZED, ToolError.CONFLICT,
    ToolError.NOT_RENEWABLE, ToolError.INVALID_ARGUMENT, ToolError.BACKEND_TIMEOUT, ToolError.BACKEND_ERROR,
}
# Common alternative spellings a backend might use
_CODE_ALIASES = {"forbidden": ToolError.PERMISSION_DENIED, "unauthenticated": ToolError.UNAUTHORIZED,
                 "validation_error": ToolError.INVALID_ARGUMENT, "bad_request": ToolError.INVALID_ARGUMENT}
_STATUS_CODES = {400: ToolError.INVALID_ARGUMENT, 401: ToolError.UNAUTHORIZED, 403: ToolError.PERMISSION_DENIED,
                 404: ToolError.NOT_FOUND, 409: ToolError.CONFLICT, 422: ToolError.INVALID_ARGUMENT}


def _seg(value: str) -> str:
    """Encode an ID as a single path segment (IDs are already pattern-validated; defense in depth)."""
    return quote(value, safe="")


class HttpLibraryToolAdapter(LibraryToolAdapter):
    def __init__(self, api_url: str, timeout: float = 5.0, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(base_url=api_url.rstrip("/"), timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------ transport

    async def _request(self, method: str, path: str, ctx: UserContext | None = None, *,
                       params: dict | None = None, json: dict | None = None,
                       idempotency_key: str | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if ctx is not None and ctx.token:
            headers["Authorization"] = f"Bearer {ctx.token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        params = {k: v for k, v in (params or {}).items() if v is not None}

        try:
            resp = await self._client.request(method, path, params=params, json=json, headers=headers)
        except httpx.TimeoutException as e:
            raise ToolError(ToolError.BACKEND_TIMEOUT, "Library backend did not respond in time.") from e
        except httpx.HTTPError as e:
            raise ToolError(ToolError.BACKEND_ERROR, "Library backend is unreachable.") from e

        try:
            body = resp.json()
        except ValueError:
            body = None

        if isinstance(body, dict) and body.get("status") == "success" and resp.is_success:
            return body.get("data")

        backend_trace = body.get("trace_id") if isinstance(body, dict) else None
        err = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
        raw_code = str(err.get("code", "")).lower()
        code = raw_code if raw_code in _KNOWN_CODES else _CODE_ALIASES.get(raw_code) or _STATUS_CODES.get(
            resp.status_code, ToolError.BACKEND_ERROR)
        if code == ToolError.BACKEND_ERROR or resp.status_code >= 500:
            # Don't relay internal server messages to the model/user
            logger.warning("Backend %s %s -> %s (backend trace %s)", method, path, resp.status_code, backend_trace)
            raise ToolError(ToolError.BACKEND_ERROR, "Library backend returned an error.")
        message = str(err.get("message") or "Request was not successful.")[:200]
        raise ToolError(code, message)

    @staticmethod
    def _parse(model, data):
        try:
            return model.model_validate(data)
        except ValidationError as e:
            logger.warning("Backend response did not match %s: %s", model.__name__, e.errors()[:3])
            raise ToolError(ToolError.BACKEND_ERROR, "Library backend returned malformed data.") from e

    def _items(self, model, data) -> list:
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ToolError(ToolError.BACKEND_ERROR, "Library backend returned malformed data.")
        return [self._parse(model, i) for i in items]

    # ------------------------------------------------------------ catalog

    async def search_resources(self, ctx, query="", limit=10, type=None, level=None,
                               updated_since: datetime | None = None):
        data = await self._request("GET", "/resources", ctx, params={
            "query": query, "limit": limit, "type": type, "level": level,
            "updated_since": updated_since.isoformat() if updated_since else None,
        })
        return self._parse(SearchResult, data)

    async def get_resource(self, ctx, resource_id):
        return self._parse(Resource, await self._request("GET", f"/resources/{_seg(resource_id)}", ctx))

    async def get_availability(self, ctx, resource_id):
        data = await self._request("GET", f"/resources/{_seg(resource_id)}/availability", ctx)
        return self._parse(Availability, data)

    async def get_resource_content(self, ctx, resource_id):
        data = await self._request("GET", f"/resources/{_seg(resource_id)}/content", ctx)
        return self._parse(ResourceContent, data)

    # ------------------------------------------------------------ account

    async def get_profile(self, ctx):
        return self._parse(User, await self._request("GET", "/me/profile", ctx))

    async def get_my_loans(self, ctx):
        return self._items(Loan, await self._request("GET", "/me/loans", ctx))

    async def get_my_reservations(self, ctx):
        return self._items(Reservation, await self._request("GET", "/me/reservations", ctx))

    # ------------------------------------------------------------ transactions

    async def create_reservation(self, ctx, resource_id, idempotency_key):
        data = await self._request("POST", "/reservations", ctx, json={"resource_id": resource_id},
                                   idempotency_key=idempotency_key)
        return self._parse(Reservation, data)

    async def renew_loan(self, ctx, loan_id, idempotency_key):
        data = await self._request("POST", f"/loans/{_seg(loan_id)}/renew", ctx, idempotency_key=idempotency_key)
        return self._parse(Loan, data)

    # ------------------------------------------------------------ analytics

    async def get_analytics_summary(self, ctx):
        return self._parse(AnalyticsSummary, await self._request("GET", "/analytics/summary", ctx))

    async def health(self) -> bool:
        try:
            await self._request("GET", "/health")
            return True
        except ToolError:
            return False
