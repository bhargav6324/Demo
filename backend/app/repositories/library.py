"""Persistence primitives only. Authorization and workflow decisions belong in services."""

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import AuditLog, Holding, IdempotencyRecord, Loan, Reservation, Resource, ResourceContent, User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: str) -> User | None:
        return self.session.scalar(select(User).options(selectinload(User.profile)).where(User.user_id == user_id))

    def by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).options(selectinload(User.profile)).where(User.email == email.strip().lower()))


class ResourceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, resource_id: str) -> Resource | None:
        return self.session.get(Resource, resource_id)

    def list(self, limit: int = 100) -> list[Resource]:
        return list(self.session.scalars(select(Resource).order_by(Resource.resource_id).limit(limit)))

    def search(self, query: str | None = None, limit: int = 20, offset: int = 0,
               resource_type: str | None = None, level: str | None = None,
               updated_since: datetime | None = None) -> tuple[list[Resource], int]:
        conditions = []
        if query and query.strip():
            term = query.strip()
            authors = func.json_each(Resource.authors).table_valued("value")
            topics = func.json_each(Resource.topics).table_valued("value")
            conditions.append(or_(
                Resource.resource_id.icontains(term, autoescape=True),
                Resource.title.icontains(term, autoescape=True),
                Resource.description.icontains(term, autoescape=True),
                select(1).select_from(authors).where(authors.c.value.icontains(term, autoescape=True)).correlate(Resource).exists(),
                select(1).select_from(topics).where(topics.c.value.icontains(term, autoescape=True)).correlate(Resource).exists(),
            ))
        if resource_type is not None:
            conditions.append(Resource.type == resource_type)
        if level is not None:
            conditions.append(Resource.level == level)
        if updated_since is not None:
            conditions.append(Resource.updated_at > updated_since)
        total = self.session.scalar(select(func.count()).select_from(Resource).where(*conditions))
        items = self.session.scalars(select(Resource).where(*conditions).order_by(
            Resource.updated_at, Resource.resource_id
        ).offset(offset).limit(limit))
        return list(items), total

    def latest_updated_at(self) -> datetime | None:
        return self.session.scalar(select(func.max(Resource.updated_at)))

    def add(self, resource: Resource):
        self.session.add(resource)
        self.session.flush()

    def content_record(self, resource_id: str) -> ResourceContent | None:
        # Internal record access; a service must authorize before returning its contents.
        return self.session.get(ResourceContent, resource_id)


class HoldingRepository:
    def __init__(self, session: Session):
        self.session = session

    def for_resource(self, resource_id: str) -> list[Holding]:
        return list(self.session.scalars(select(Holding).where(Holding.resource_id == resource_id).order_by(Holding.holding_id)))

    def try_allocate(self, holding_id: str) -> bool:
        # The caller must put this and the resulting loan/hold in the same write transaction.
        result = self.session.execute(update(Holding).where(
            Holding.holding_id == holding_id, Holding.available_copies > 0
        ).values(available_copies=Holding.available_copies - 1))
        return result.rowcount == 1


class CirculationRepository:
    def __init__(self, session: Session):
        self.session = session

    def loans_for_user(self, user_id: str) -> list[Loan]:
        return list(self.session.scalars(select(Loan).where(Loan.user_id == user_id).order_by(Loan.loan_id)))

    def loan_for_user(self, loan_id: str, user_id: str) -> Loan | None:
        return self.session.scalar(select(Loan).where(Loan.loan_id == loan_id, Loan.user_id == user_id))

    def get_loan(self, loan_id: str) -> Loan | None:
        return self.session.get(Loan, loan_id)

    def open_reservation(self, user_id: str, resource_id: str) -> Reservation | None:
        return self.session.scalar(select(Reservation).where(
            Reservation.user_id == user_id, Reservation.resource_id == resource_id,
            Reservation.status.in_(["active", "waitlisted"]),
        ))

    def has_other_hold(self, resource_id: str, user_id: str) -> bool:
        return self.session.scalar(select(Reservation.reservation_id).where(
            Reservation.resource_id == resource_id, Reservation.user_id != user_id,
            Reservation.status.in_(["active", "waitlisted"]),
        ).limit(1)) is not None

    def waitlist(self, resource_id: str) -> list[Reservation]:
        return list(self.session.scalars(select(Reservation).where(
            Reservation.resource_id == resource_id, Reservation.status == "waitlisted",
        ).order_by(Reservation.queue_position, Reservation.created_at, Reservation.reservation_id)))

    def add_reservation(self, reservation: Reservation):
        self.session.add(reservation)
        self.session.flush()

    def reservations_for_user(self, user_id: str) -> list[Reservation]:
        return list(self.session.scalars(select(Reservation).where(Reservation.user_id == user_id).order_by(Reservation.reservation_id)))

    def waitlist_count(self, resource_id: str) -> int:
        return self.session.scalar(select(func.count()).select_from(Reservation).where(
            Reservation.resource_id == resource_id, Reservation.status == "waitlisted"
        ))


class IdempotencyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: str, operation: str, key: str) -> IdempotencyRecord | None:
        return self.session.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id, IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        ))

    def add(self, record: IdempotencyRecord):
        self.session.add(record)
        self.session.flush()


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, record: AuditLog):
        self.session.add(record)
        self.session.flush()
