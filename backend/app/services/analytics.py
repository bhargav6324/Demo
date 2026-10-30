from app.core.database import Database
from app.models import User
from app.models.base import utc_now
from app.repositories.analytics import AnalyticsRepository
from app.repositories.library import UserRepository
from app.schemas.domain import AnalyticsSummary, PopularResource
from app.security.permissions import require_librarian
from app.security.tokens import unauthorized


class AnalyticsService:
    def __init__(self, database: Database):
        self.database = database

    def summary(self, actor: User) -> AnalyticsSummary:
        # Permission and all aggregates share a single read transaction/snapshot.
        with self.database.session() as session:
            user = UserRepository(session).get(actor.user_id)
            if user is None:
                raise unauthorized()
            require_librarian(user)
            repository = AnalyticsRepository(session)
            counts = repository.counts(utc_now())
            popular = [PopularResource(**item) for item in repository.popular_resources()]
            return AnalyticsSummary(**counts, popular_resources=popular)
