"""Identity adapters turn a bearer token into a UserContext.

Mock mode maps fixture tokens to users. HTTP mode validates the token
against the backend's GET /auth/me."""
import hashlib
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from app.adapters.errors import ToolError
from app.auth.context import UserContext
from app.schemas.library import User

if TYPE_CHECKING:
    from app.adapters.http_adapter import HttpLibraryToolAdapter


class IdentityAdapter(ABC):
    @abstractmethod
    async def authenticate(self, token: str) -> UserContext:
        """Return the caller's context or raise ToolError(UNAUTHORIZED)."""


class MockIdentityAdapter(IdentityAdapter):
    def __init__(self, fixtures_dir: Path):
        entries = json.loads((Path(fixtures_dir) / "users.json").read_text(encoding="utf-8"))
        self._by_token = {e["token"]: e["user"] for e in entries}

    async def authenticate(self, token: str) -> UserContext:
        user = self._by_token.get(token)
        if user is None:
            raise ToolError(ToolError.UNAUTHORIZED, "Invalid or expired token.")
        return UserContext(user_id=user["user_id"], name=user["name"], role=user["role"], token=token)


class HttpIdentityAdapter(IdentityAdapter):
    """Validates the bearer token with the backend's GET /auth/me.
    Successful lookups are cached briefly (keyed by a hash, not the raw token)."""

    def __init__(self, adapter: "HttpLibraryToolAdapter", cache_seconds: float = 60.0, clock=time.monotonic):
        self._adapter = adapter
        self._ttl = cache_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, UserContext]] = {}

    async def authenticate(self, token: str) -> UserContext:
        key = hashlib.sha256(token.encode()).hexdigest()
        hit = self._cache.get(key)
        if hit and hit[0] > self._clock():
            return hit[1]

        probe = UserContext(user_id="", name="", role="student", token=token)
        data = await self._adapter._request("GET", "/auth/me", probe)
        if isinstance(data, dict) and isinstance(data.get("user"), dict):
            data = data["user"]  # tolerate {"user": {...}} as well as the bare user object
        user = self._adapter._parse(User, data)
        ctx = UserContext(user_id=user.user_id, name=user.name, role=user.role, token=token)
        self._cache[key] = (self._clock() + self._ttl, ctx)
        return ctx
