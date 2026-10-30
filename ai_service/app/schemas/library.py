"""Canonical library models, matching the backend handoff contract
(BACKEND_API_HANDOFF.md, 2026-10-30). Both the mock and HTTP adapters
return exactly these shapes."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["student", "faculty", "researcher", "librarian"]
ResourceType = Literal["book", "journal", "paper", "ebook", "dissertation"]
Level = Literal["beginner", "intermediate", "advanced"]
# public: anyone | authenticated: any logged-in role | restricted: librarian only (prototype rule)
AccessLevel = Literal["public", "authenticated", "restricted"]


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
    """GET /auth/me returns identity fields; GET /me/profile adds courses/interests."""
    user_id: str
    name: str
    email: str = ""
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
    fine_amount: Decimal  # decimal JSON string on the wire, e.g. "0.00"
    status: Literal["active", "overdue", "returned"]


class Reservation(BaseModel):
    reservation_id: str
    resource_id: str
    status: Literal["active", "waitlisted", "cancelled", "fulfilled"]
    queue_position: int | None = None  # positive only while waitlisted


class SearchResult(BaseModel):
    items: list[Resource]
    total: int


class CatalogSearchResult(SearchResult):
    """search_catalog tool output: set when requested filters matched nothing and were dropped."""
    filters_relaxed: dict[str, str] | None = None
    note: str | None = None


class ResourceContent(BaseModel):
    """GET /resources/{id}/content."""
    resource_id: str
    content: str
    source: str  # human-readable provenance
    updated_at: datetime | None = None


class PopularResource(BaseModel):
    resource_id: str
    title: str
    loan_count: int


class AnalyticsSummary(BaseModel):
    """GET /analytics/summary (librarian only). Extra fields are passed through."""
    model_config = ConfigDict(extra="allow")

    total_resources: int
    active_loans: int
    overdue_loans: int
    active_reservations: int
    popular_resources: list[PopularResource] = Field(default_factory=list)
