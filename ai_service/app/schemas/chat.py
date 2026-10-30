"""Public AI chat API contract (consumed by the frontend)."""
from typing import Literal

from pydantic import BaseModel, Field

Outcome = Literal["answered", "not_found", "refused", "needs_confirmation"]


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatResource(BaseModel):
    resource_id: str
    title: str
    reason: str
    available_copies: int | None = None  # only present when verified by get_availability


class Citation(BaseModel):
    resource_id: str
    source_type: str  # "catalog" | "document" | "chunk"
    source_id: str
    title: str


class ProposedAction(BaseModel):
    action_id: str
    action_type: Literal["reservation", "renewal"]
    resource_id: str | None = None
    loan_id: str | None = None
    description: str


class ChatResponseData(BaseModel):
    conversation_id: str
    outcome: Outcome
    assistant_message: str
    intent: str
    resources: list[ChatResource] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    proposed_action: ProposedAction | None = None


class ConfirmActionRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=128)


class ConfirmActionData(BaseModel):
    """completed = the backend applied it; rejected = a library rule refused it (action
    discarded); failed = temporary outage, nothing changed (action kept, safe to retry)."""
    action_id: str
    action_type: Literal["reservation", "renewal"]
    transaction_status: Literal["completed", "rejected", "failed"]
    transaction_id: str | None = None  # reservation_id or loan_id of the affected record
    reservation_id: str | None = None
    loan_id: str | None = None
    message: str
    details: dict | None = None
