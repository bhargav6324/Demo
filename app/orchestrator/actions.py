"""Short-lived server-side store for proposed state-changing actions.

The client only ever holds an opaque action_id. Owner, tool name and
validated arguments stay here, so a confirmation cannot alter them."""
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class PendingAction:
    action_id: str
    owner: str
    tool: str
    args: dict
    action_type: str
    description: str
    expires_at: float
    title: str = ""
    # Reused on retries so the backend never applies the action twice
    idempotency_key: str = field(default_factory=lambda: secrets.token_hex(16))
    # Set once executed; repeated confirms (double clicks) return this instead of re-running
    result: dict | None = None


class ActionStore:
    def __init__(self, ttl_seconds: int, clock=time.monotonic):
        self.ttl = ttl_seconds
        self.clock = clock
        self._items: dict[str, PendingAction] = {}

    def create(self, owner: str, tool: str, args: dict, action_type: str, description: str,
               title: str = "") -> PendingAction:
        self._evict()
        action = PendingAction(
            action_id=f"act-{secrets.token_urlsafe(16)}",
            owner=owner, tool=tool, args=dict(args), action_type=action_type,
            description=description, expires_at=self.clock() + self.ttl, title=title,
        )
        self._items[action.action_id] = action
        return action

    def get(self, action_id: str) -> PendingAction | None:
        action = self._items.get(action_id)
        if action and action.expires_at < self.clock():
            del self._items[action_id]
            return None
        return action

    def remove(self, action_id: str) -> None:
        self._items.pop(action_id, None)

    def _evict(self) -> None:
        now = self.clock()
        for aid in [a for a, v in self._items.items() if v.expires_at < now]:
            del self._items[aid]
