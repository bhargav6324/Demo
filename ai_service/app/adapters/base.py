"""LibraryToolAdapter: the only path from the AI service to library data.

Mock and HTTP implementations are interchangeable; the rest of the service
depends on this interface alone. Methods return canonical models and raise
ToolError on failure. Identity always comes from `ctx`, never from arguments."""
from abc import ABC, abstractmethod
from datetime import datetime

from app.auth.context import UserContext
from app.schemas.library import (
    AnalyticsSummary,
    Availability,
    Loan,
    Reservation,
    Resource,
    ResourceContent,
    SearchResult,
    User,
)


class LibraryToolAdapter(ABC):
    @abstractmethod
    async def search_resources(
        self,
        ctx: UserContext | None,
        query: str = "",
        limit: int = 20,
        type: str | None = None,
        level: str | None = None,
        updated_since: datetime | None = None,
        offset: int = 0,
    ) -> SearchResult:
        """Backend GET /resources: literal case-insensitive substring match on
        id/title/description/authors/topics, ordered by updated_at then
        resource_id, limit 1-100 with offset paging. Not relevance-ranked."""

    @abstractmethod
    async def get_resource(self, ctx: UserContext | None, resource_id: str) -> Resource: ...

    @abstractmethod
    async def get_availability(self, ctx: UserContext | None, resource_id: str) -> Availability: ...

    @abstractmethod
    async def get_resource_content(self, ctx: UserContext, resource_id: str) -> ResourceContent: ...

    @abstractmethod
    async def get_profile(self, ctx: UserContext) -> User: ...

    @abstractmethod
    async def get_my_loans(self, ctx: UserContext) -> list[Loan]: ...

    @abstractmethod
    async def get_my_reservations(self, ctx: UserContext) -> list[Reservation]: ...

    @abstractmethod
    async def create_reservation(
        self, ctx: UserContext, resource_id: str, idempotency_key: str
    ) -> Reservation: ...

    @abstractmethod
    async def renew_loan(self, ctx: UserContext, loan_id: str, idempotency_key: str) -> Loan: ...

    @abstractmethod
    async def get_analytics_summary(self, ctx: UserContext) -> AnalyticsSummary: ...

    async def health(self) -> bool:
        return True
