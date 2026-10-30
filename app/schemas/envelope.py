"""Standard response envelopes shared with the backend and frontend."""
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


def new_trace_id() -> str:
    return uuid.uuid4().hex


class ErrorBody(BaseModel):
    code: str
    message: str


class SuccessEnvelope(BaseModel):
    status: Literal["success"] = "success"
    data: Any
    trace_id: str = Field(default_factory=new_trace_id)


class ErrorEnvelope(BaseModel):
    status: Literal["error"] = "error"
    error: ErrorBody
    trace_id: str = Field(default_factory=new_trace_id)
