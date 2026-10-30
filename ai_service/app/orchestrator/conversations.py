"""In-memory conversation history, scoped to the owning user."""
import secrets
import time
from dataclasses import dataclass, field

MAX_TURNS = 12  # messages kept (user + assistant)
TTL_SECONDS = 2 * 60 * 60


class ConversationAccessError(Exception):
    pass


@dataclass
class Conversation:
    conversation_id: str
    owner: str | None
    messages: list[dict] = field(default_factory=list)
    updated: float = field(default_factory=time.monotonic)


class ConversationStore:
    def __init__(self):
        self._items: dict[str, Conversation] = {}

    def get_or_create(self, conversation_id: str | None, owner: str | None) -> Conversation:
        self._evict()
        if conversation_id and (conv := self._items.get(conversation_id)):
            if conv.owner != owner:
                raise ConversationAccessError("Conversation not found.")
            return conv
        cid = conversation_id or f"conv-{secrets.token_urlsafe(9)}"
        conv = Conversation(cid, owner)
        self._items[cid] = conv
        return conv

    def append(self, conv: Conversation, user_text: str, assistant_text: str) -> None:
        conv.messages += [{"role": "user", "content": user_text}, {"role": "assistant", "content": assistant_text}]
        conv.messages = conv.messages[-MAX_TURNS:]
        conv.updated = time.monotonic()

    def _evict(self) -> None:
        cutoff = time.monotonic() - TTL_SECONDS
        for cid in [c for c, v in self._items.items() if v.updated < cutoff]:
            del self._items[cid]
