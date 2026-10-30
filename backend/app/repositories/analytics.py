"""Aggregate library data without exposing patron-level records."""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Loan, Reservation, Resource


class AnalyticsRepository:
    def __init__(self, session: Session):
        self.session = session

    def counts(self, now: datetime) -> dict[str, int]:
        outstanding = Loan.status.in_(["active", "overdue"])
        statement = select(
            select(func.count()).select_from(Resource).scalar_subquery().label("total_resources"),
            select(func.count()).select_from(Loan).where(outstanding).scalar_subquery().label("active_loans"),
            select(func.count()).select_from(Loan).where(
                outstanding, or_(Loan.status == "overdue", Loan.due_at <= now)
            ).scalar_subquery().label("overdue_loans"),
            select(func.count()).select_from(Reservation).where(
                Reservation.status.in_(["active", "waitlisted"])
            ).scalar_subquery().label("active_reservations"),
        )
        return dict(self.session.execute(statement).mappings().one())

    def popular_resources(self, limit: int = 5) -> list[dict]:
        loan_count = func.count(Loan.loan_id).label("loan_count")
        statement = (
            select(Resource.resource_id, Resource.title, loan_count)
            .join(Loan, Loan.resource_id == Resource.resource_id)
            .group_by(Resource.resource_id, Resource.title)
            .order_by(loan_count.desc(), Resource.resource_id.asc())
            .limit(limit)
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]
