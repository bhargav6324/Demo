"""Canonical library models. These mirror the agreed backend contract exactly;
both the mock and HTTP adapters must return these shapes."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["student", "faculty", "researcher", "librarian"]
ResourceType = Literal["book", "ebook", "journal", "paper", "dissertation", "learning_path"]
Level = Literal["beginner", "intermediate", "advanced"]
# public: anyone | university: any authenticated member | restricted: faculty/researcher/librarian
AccessLevel = Literal["public", "university", "restricted"]


class Resource(BaseModel):
    resource_id: str
    title: str
    authors: list[str]
    type: ResourceType
    description: str
    topics: list[str]
    level: Level
    access_level: AccessLevel
    updated_at: datetime


class Location(BaseModel):
    branch: str
    shelf: str
    available_copies: int


class Availability(BaseModel):
    resource_id: str
    total_copies: int
    available_copies: int
    waitlist_count: int
    locations: list[Location]


class User(BaseModel):
    user_id: str
    name: str
    email: str
    role: Role
    courses: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)


class Loan(BaseModel):
    loan_id: str
    resource_id: str
    resource_title: str
    borrowed_at: datetime
    due_at: datetime
    renewable: bool
    fine_amount: float
    status: Literal["active", "overdue", "returned"]


class Reservation(BaseModel):
    reservation_id: str
    resource_id: str
    status: Literal["waitlisted", "ready_for_pickup", "cancelled", "fulfilled"]
    queue_position: int


class SearchResult(BaseModel):
    items: list[Resource]
    total: int


class ResourceContent(BaseModel):
    """Authorized source text for a resource (GET /resources/{id}/content).
    Shape is our proposal to the backend team: confirm before integration."""
    resource_id: str
    title: str
    source_type: str
    access_level: AccessLevel
    text: str


class AnalyticsSummary(BaseModel):
    """The README contract does not fix this shape, so every field is optional
    and unknown backend fields are passed through unchanged."""
    model_config = ConfigDict(extra="allow")

    generated_at: datetime | None = None
    top_waitlisted: list[dict[str, Any]] = Field(default_factory=list)
    circulation_trend: list[dict[str, Any]] = Field(default_factory=list)
    overdue_summary: dict[str, Any] = Field(default_factory=dict)
    utilization_by_type: list[dict[str, Any]] = Field(default_factory=list)
    catalog_gaps: list[dict[str, Any]] = Field(default_factory=list)
