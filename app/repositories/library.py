"""Persistence primitives only. Authorization and workflow decisions belong in services."""

from sqlalchemy import select, update
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

    def reservations_for_user(self, user_id: str) -> list[Reservation]:
        return list(self.session.scalars(select(Reservation).where(Reservation.user_id == user_id).order_by(Reservation.reservation_id)))


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
