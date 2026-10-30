"""Per-request audit trail: which tools ran, with what (redacted) arguments,
outcome, error code and latency. Logged as JSON lines; never contains tokens."""
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from app.schemas.envelope import new_trace_id

logger = logging.getLogger("smartlibrary.audit")

_SECRET_KEYS = {"token", "authorization", "password", "api_key", "secret", "jwt"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "***" if k.lower() in _SECRET_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


@dataclass
class ToolCallRecord:
    tool: str
    args: dict
    status: str
    error_code: str | None
    latency_ms: float


@dataclass
class Trace:
    trace_id: str = field(default_factory=new_trace_id)
    user_id: str | None = None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    def record(self, tool: str, args: dict, status: str, error_code: str | None, latency_ms: float) -> None:
        rec = ToolCallRecord(tool, redact(args), status, error_code, round(latency_ms, 2))
        self.tool_calls.append(rec)
        logger.info(json.dumps({"event": "tool_call", "trace_id": self.trace_id, "user_id": self.user_id, **asdict(rec)}))

    @property
    def tool_names(self) -> list[str]:
        return [r.tool for r in self.tool_calls]
