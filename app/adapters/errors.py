class ToolError(Exception):
    """Raised by adapters for any non-success outcome. `code` is a stable,
    machine-readable value the orchestrator uses to pick the chat outcome."""

    # Codes shared by every adapter
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    UNAUTHORIZED = "unauthorized"
    CONFLICT = "conflict"
    NOT_RENEWABLE = "not_renewable"
    INVALID_ARGUMENT = "invalid_argument"
    BACKEND_TIMEOUT = "backend_timeout"
    BACKEND_ERROR = "backend_error"

    RETRYABLE = {BACKEND_TIMEOUT, BACKEND_ERROR}

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def retryable(self) -> bool:
        return self.code in self.RETRYABLE

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
