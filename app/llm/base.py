"""Provider-neutral LLM interface used by the orchestrator.

Conversation messages are plain dicts:
  {"role": "user", "content": str}
  {"role": "assistant", "content": str | None, "tool_calls": [ToolCall], "raw": provider-native turn}
  {"role": "tool", "tool_call_id": str, "name": str, "content": dict}
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Internal pseudo-tool the model calls to end its turn with a structured answer.
# It is handled by the orchestrator and is never part of the tool registry.
FINAL_ANSWER = "final_answer"

INTENTS = [
    "search", "availability", "recommendation", "account", "reservation", "renewal",
    "research", "analytics", "general", "out_of_scope",
]

FINAL_ANSWER_DECLARATION = {
    "name": FINAL_ANSWER,
    "description": (
        "Finish the turn with the answer for the user. Call this exactly once, after any tools you need. "
        "List every catalog resource your message refers to in `resources` (IDs must come from tool results)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Answer shown to the user, grounded only in tool results."},
            "intent": {"type": "string", "enum": INTENTS},
            "resources": {
                "type": "array",
                "description": "Resources referenced in the message, most relevant first.",
                "items": {
                    "type": "object",
                    "properties": {
                        "resource_id": {"type": "string"},
                        "reason": {"type": "string", "description": "Short why-this-resource explanation."},
                    },
                    "required": ["resource_id"],
                },
            },
            "abstain": {
                "type": "string",
                "enum": ["none", "not_found", "privacy", "unauthorized", "out_of_scope"],
                "description": "Set when you cannot answer: not_found (no matching verified data), privacy (another person's data), unauthorized, out_of_scope.",
            },
        },
        "required": ["message", "intent", "abstain"],
    },
}


class LLMError(Exception):
    """Provider failure (network, quota, malformed output)."""

    def __init__(self, message: str, code: str = "llm_unavailable"):
        super().__init__(message)
        self.code = code  # "llm_rate_limited" | "llm_unavailable"


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # provider-native assistant turn, replayed verbatim on the next call


class LLMClient(ABC):
    @abstractmethod
    async def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...
