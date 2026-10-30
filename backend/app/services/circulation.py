"""Deterministic, authenticated circulation with atomic persistent retry results."""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.core.database import Database
from app.core.errors import APIError
from app.models import AuditLog, IdempotencyRecord, Reservation, User
from app.models.base import utc_now
from app.repositories.library import (
    AuditRepository, CirculationRepository, HoldingRepository, IdempotencyRepository,
    ResourceRepository, UserRepository,
)
from app.schemas.domain import (
    Loan as LoanSchema, LoanList, Reservation as ReservationSchema, ReservationCreate, ReservationList,
)
from app.security.permissions import require_owner
from app.security.tokens import unauthorized

RENEWAL_DAYS = 14
MAX_RENEWALS = 2


@dataclass
class CirculationResult:
    data: LoanSchema | ReservationSchema
    status_code: int
    replayed: bool


def reservation_data(reservation: Reservation) -> ReservationSchema:
    return ReservationSchema(reservation_id=reservation.reservation_id, resource_id=reservation.resource_id,
                             status=reservation.status, queue_position=reservation.queue_position)


def current_user(session, actor: User) -> User:
    user = UserRepository(session).get(actor.user_id)
    if user is None:
        raise unauthorized()
    return user


def renewal_blocker(loan, repository: CirculationRepository, now) -> str | None:
    if loan.status == "returned":
        return "Returned loans cannot be renewed"
    if loan.status == "overdue" or loan.due_at <= now:
        return "Overdue loans cannot be renewed"
    if loan.fine_amount_minor > 0:
        return "Loans with outstanding fines cannot be renewed"
    if loan.renewal_count >= MAX_RENEWALS:
        return "Maximum renewal count has been reached"
    if repository.has_other_hold(loan.resource_id, loan.user_id):
        return "Another user has an open hold for this resource"
    return None


def loan_data(loan, session, now) -> LoanSchema:
    resource = ResourceRepository(session).get(loan.resource_id)
    status = "returned" if loan.status == "returned" else "overdue" if loan.status == "overdue" or loan.due_at <= now else "active"
    return LoanSchema(
        loan_id=loan.loan_id, resource_id=loan.resource_id, resource_title=resource.title,
        borrowed_at=loan.borrowed_at, due_at=loan.due_at,
        renewable=renewal_blocker(loan, CirculationRepository(session), now) is None,
        fine_amount=loan.fine_amount, status=status,
    )


class CirculationService:
    def __init__(self, database: Database):
        self.database = database

    def loans(self, actor: User) -> LoanList:
        with self.database.session() as session:
            user = current_user(session, actor)
            now = utc_now()
            return LoanList(items=[loan_data(loan, session, now)
                                   for loan in CirculationRepository(session).loans_for_user(user.user_id)])

    def reservations(self, actor: User) -> ReservationList:
        with self.database.session() as session:
            user = current_user(session, actor)
            return ReservationList(items=[reservation_data(item) for item in
                CirculationRepository(session).reservations_for_user(user.user_id)])

    def _transaction(self, actor, operation_name, action, key, payload, operation, schema, trace_id, authorize=None):
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        failure = None
        try:
            with self.database.write_session() as session:
                user = UserRepository(session).get(actor.user_id)
                try:
                    if user is None:
                        raise unauthorized()
                    if authorize:
                        authorize(session, user)
                    previous = IdempotencyRepository(session).get(user.user_id, operation_name, key)
                    if previous:
                        if previous.request_hash != fingerprint:
                            raise APIError(409, "idempotency_conflict", "Idempotency-Key was already used with a different request")
                        data = schema.model_validate(previous.response_data)
                        status_code = previous.status_code
                        replayed = True
                    else:
                        # Business failures roll back any allocations/promotions; the outer
                        # transaction can still persist a sanitized failure audit entry.
                        with session.begin_nested():
                            data, status_code = operation(session, user)
                            IdempotencyRepository(session).add(IdempotencyRecord(
                                user_id=user.user_id, operation=operation_name, key=key,
                                request_hash=fingerprint, status_code=status_code,
                                response_data=data.model_dump(mode="json"),
                            ))
                        replayed = False
                    result = "replayed" if replayed else "success"
                except (HTTPException, APIError) as exc:
                    failure = exc
                    result = "not_found" if exc.status_code == 404 else "conflict" if exc.status_code == 409 else "denied"
                AuditRepository(session).add(AuditLog(
                    user_id=user.user_id if user else None, action=action, result=result, trace_id=trace_id,
                ))
        except OperationalError as exc:
            error_code = getattr(exc.orig, "sqlite_errorcode", 0)
            if (error_code & 255) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise APIError(409, "database_busy", "Database is busy; retry with the same Idempotency-Key") from None
            raise
        if failure:
            raise failure
        return CirculationResult(data, status_code, replayed)

    def _allocate(self, session, resource_id):
        holdings = HoldingRepository(session)
        for holding in holdings.for_resource(resource_id):
            if holdings.try_allocate(holding.holding_id):
                return holding.holding_id
        return None

    def _promote_waitlist(self, session, resource_id, actor, trace_id):
        repository = CirculationRepository(session)
        for reservation in repository.waitlist(resource_id):
            holding_id = self._allocate(session, resource_id)
            if holding_id is None:
                break
            reservation.status = "active"
            reservation.queue_position = None
            reservation.allocated_holding_id = holding_id
            session.flush()
            AuditRepository(session).add(AuditLog(user_id=actor.user_id, action="circulation.waitlist_promote",
                                                 result="success", trace_id=trace_id))
        # Update ascending positions and flush individually to respect unique queue slots.
        waiting = repository.waitlist(resource_id)
        for position, reservation in enumerate(waiting, 1):
            reservation.queue_position = position
            session.flush()
        return len(waiting)

    def reserve(self, body: ReservationCreate, actor: User, key: str, trace_id: str) -> CirculationResult:
        def operation(session, user):
            if ResourceRepository(session).get(body.resource_id) is None:
                raise HTTPException(404, "Resource not found")
            repository = CirculationRepository(session)
            if repository.open_reservation(user.user_id, body.resource_id):
                raise APIError(409, "duplicate_reservation", "An open reservation already exists for this resource")
            queue_length = self._promote_waitlist(session, body.resource_id, user, trace_id)
            holding_id = self._allocate(session, body.resource_id)
            reservation = Reservation(
                user_id=user.user_id, resource_id=body.resource_id,
                status="active" if holding_id else "waitlisted",
                queue_position=None if holding_id else queue_length + 1,
                allocated_holding_id=holding_id,
            )
            repository.add_reservation(reservation)
            return reservation_data(reservation), 201
        return self._transaction(actor, "POST /reservations", "circulation.reserve", key,
                                 body.model_dump(), operation, ReservationSchema, trace_id)

    def renew(self, loan_id: str, actor: User, key: str, trace_id: str) -> CirculationResult:
        def authorize(session, user):
            loan = CirculationRepository(session).get_loan(loan_id)
            if loan is None:
                raise HTTPException(404, "Loan not found")
            require_owner(user, loan.user_id)

        def operation(session, user):
            repository = CirculationRepository(session)
            loan = repository.get_loan(loan_id)
            now = utc_now()
            reason = renewal_blocker(loan, repository, now)
            if reason:
                raise APIError(409, "renewal_not_allowed", reason)
            loan.due_at += timedelta(days=RENEWAL_DAYS)
            loan.renewal_count += 1
            session.flush()
            return loan_data(loan, session, now), 200
        return self._transaction(actor, f"POST /loans/{loan_id}/renew", "circulation.renew", key,
                                 {}, operation, LoanSchema, trace_id, authorize=authorize)
