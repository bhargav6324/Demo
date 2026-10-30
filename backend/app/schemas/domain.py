"""Initial public contracts; policy-dependent details are recorded in docs/API_CONTRACT.md."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, SecretStr, StringConstraints, field_validator, model_validator

from app.schemas.common import ContractModel, StableID, UTCTimestamp

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Count = Annotated[int, Field(ge=0)]


class Role(StrEnum):
    student = "student"
    faculty = "faculty"
    researcher = "researcher"
    librarian = "librarian"


class ResourceType(StrEnum):
    book = "book"
    journal = "journal"
    paper = "paper"
    ebook = "ebook"
    dissertation = "dissertation"


class Level(StrEnum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class AccessLevel(StrEnum):
    public = "public"
    authenticated = "authenticated"
    restricted = "restricted"


class LoginRequest(ContractModel):
    email: Annotated[str, Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class UserIdentity(ContractModel):
    user_id: StableID
    name: NonEmpty
    email: str
    role: Role


class Profile(ContractModel):
    courses: list[str]
    interests: list[str]


class User(UserIdentity):
    courses: list[str]
    interests: list[str]


class LoginData(ContractModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: Annotated[int, Field(gt=0)]
    user: User


class ResourceCreate(ContractModel):
    title: NonEmpty
    authors: list[NonEmpty] = Field(min_length=1)
    type: ResourceType
    description: str
    topics: list[NonEmpty]
    level: Level
    access_level: AccessLevel


class Resource(ResourceCreate):
    resource_id: StableID
    updated_at: UTCTimestamp


class ResourcePatch(ContractModel):
    title: NonEmpty | None = None
    authors: list[NonEmpty] | None = Field(default=None, min_length=1)
    type: ResourceType | None = None
    description: str | None = None
    topics: list[NonEmpty] | None = None
    level: Level | None = None
    access_level: AccessLevel | None = None

    @model_validator(mode="after")
    def actual_update(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Provide at least one non-null field; omit unchanged fields")
        return self


class ResourceList(ContractModel):
    items: list[Resource]
    total: Count


class Location(ContractModel):
    branch: str
    shelf: str
    available_copies: Count


class Availability(ContractModel):
    resource_id: StableID
    total_copies: Count
    available_copies: Count
    waitlist_count: Count
    locations: list[Location]


class ResourceContent(ContractModel):
    resource_id: StableID
    content: str = Field(description="Authorized plain-text content or excerpt only")
    source: str = Field(description="Human-readable source/provenance; no credential-bearing URLs")
    updated_at: UTCTimestamp


class Loan(ContractModel):
    loan_id: StableID
    resource_id: StableID
    resource_title: str
    borrowed_at: UTCTimestamp
    due_at: UTCTimestamp
    renewable: bool
    fine_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
    status: Literal["active", "returned", "overdue"]


class LoanList(ContractModel):
    items: list[Loan]


class ReservationCreate(ContractModel):
    resource_id: StableID


class Reservation(ContractModel):
    reservation_id: StableID
    resource_id: StableID
    status: Literal["active", "waitlisted", "cancelled", "fulfilled"]
    queue_position: Annotated[int, Field(ge=1)] | None


class ReservationList(ContractModel):
    items: list[Reservation]


class PopularResource(ContractModel):
    resource_id: StableID
    title: str
    loan_count: Count


class AnalyticsSummary(ContractModel):
    total_resources: Count
    active_loans: Count
    overdue_loans: Count
    active_reservations: Count
    popular_resources: list[PopularResource]
