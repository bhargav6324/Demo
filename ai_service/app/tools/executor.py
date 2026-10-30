"""Validates and runs LLM tool requests. Pipeline per call:
allowlist -> argument schema -> auth/role -> (confirmation gate) -> handler
-> result validation -> trace record. Never raises; always returns a ToolResult."""
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError
from pydantic_core import to_jsonable_python

from app.adapters.errors import ToolError
from app.observability.trace import Trace
from app.tools.registry import ExecContext, ToolRegistry, ToolSpec

logger = logging.getLogger("smartlibrary.executor")

Status = Literal["success", "error", "rejected", "confirmation_required"]


@dataclass
class ToolResult:
    tool: str
    args: dict
    status: Status
    data: Any = None              # JSON-serializable dict on success / precheck data
    error: dict | None = None     # {"code", "message"}

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def error_code(self) -> str | None:
        return self.error["code"] if self.error else None

    def for_llm(self) -> dict:
        """What the model sees back: data or error, nothing server-internal."""
        if self.ok:
            return {"status": "success", "data": self.data}
        if self.status == "confirmation_required":
            return {"status": "confirmation_required",
                    "message": "Action proposed to the user for explicit confirmation; it has NOT been executed.",
                    "data": self.data}
        return {"status": "error", "error": self.error}


def _to_json(value: Any) -> Any:
    """Models, datetimes and nested containers -> plain JSON types."""
    return to_jsonable_python(value)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._validators = {
            name: Draft202012Validator(registry.get(name).input_schema) for name in registry.names()
        }

    def _reject(self, trace: Trace, name: str, args: Any, code: str, message: str, start: float) -> ToolResult:
        safe_args = args if isinstance(args, dict) else {"_raw": str(args)[:200]}
        trace.record(name, safe_args, "rejected", code, (time.perf_counter() - start) * 1000)
        return ToolResult(name, safe_args, "rejected", error={"code": code, "message": message})

    def validate(self, name: str, args: Any, ec: ExecContext) -> tuple[ToolSpec | None, str | None, str | None]:
        """Static checks shared by chat execution and action confirmation.
        Returns (spec, error_code, error_message)."""
        spec = self.registry.get(name)
        if spec is None:
            return None, "unknown_tool", f"Tool '{name}' is not registered."
        if not isinstance(args, dict):
            return spec, ToolError.INVALID_ARGUMENT, "Tool arguments must be an object."
        errors = sorted(self._validators[name].iter_errors(args), key=lambda e: list(e.path))
        if errors:
            return spec, ToolError.INVALID_ARGUMENT, "; ".join(e.message for e in errors[:3])
        if spec.requires_auth and ec.user is None:
            return spec, ToolError.UNAUTHORIZED, "You need to sign in for this request."
        if spec.allowed_roles is not None and (ec.user is None or ec.user.role not in spec.allowed_roles):
            return spec, ToolError.PERMISSION_DENIED, f"'{name}' is not permitted for your role."
        return spec, None, None

    async def execute(self, name: str, args: Any, ec: ExecContext, trace: Trace, *, confirmed: bool = False) -> ToolResult:
        start = time.perf_counter()
        spec, code, message = self.validate(name, args, ec)
        if code:
            return self._reject(trace, name, args, code, message, start)

        # State-changing tools: run only the read-only precheck unless explicitly confirmed
        use_precheck = spec.requires_confirmation and not confirmed
        handler = spec.precheck if use_precheck else spec.handler
        if spec.requires_confirmation and confirmed and not ec.idempotency_key:
            return self._reject(trace, name, args, ToolError.INVALID_ARGUMENT, "Missing idempotency key.", start)

        try:
            raw = await handler(ec, args)
            if spec.output_type is not None and not use_precheck:
                raw = TypeAdapter(spec.output_type).validate_python(raw)
            data = _to_json(raw)
            status: Status = "confirmation_required" if use_precheck else "success"
            result = ToolResult(name, args, status, data=data)
        except ToolError as e:
            result = ToolResult(name, args, "error", error=e.to_dict())
        except ValidationError as e:
            logger.error("Tool %s returned an invalid result: %s", name, e)
            result = ToolResult(name, args, "error",
                                error={"code": ToolError.BACKEND_ERROR, "message": "Backend returned malformed data."})
        except Exception:  # noqa: BLE001 - tools must never crash the chat request
            logger.exception("Tool %s failed unexpectedly", name)
            result = ToolResult(name, args, "error",
                                error={"code": ToolError.BACKEND_ERROR, "message": "Unexpected tool failure."})

        trace.record(name, args, result.status, result.error_code, (time.perf_counter() - start) * 1000)
        return result
