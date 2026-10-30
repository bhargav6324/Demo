from datetime import datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(timezone.utc)


UTCTimestamp = Annotated[datetime, AfterValidator(normalize_utc)]
StableID = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


T = TypeVar("T")


class SuccessResponse(ContractModel, Generic[T]):
    status: Literal["success"] = "success"
    data: T
    trace_id: str


class ErrorDetail(ContractModel):
    code: str
    message: str


class ErrorResponse(ContractModel):
    status: Literal["error"] = "error"
    error: ErrorDetail
    trace_id: str


class HealthData(ContractModel):
    service: str
    version: str
    status: Literal["ok"] = "ok"
