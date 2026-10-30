from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
import sqlite3
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.errors import APIError
from app.main import create_app
from app.models import AuditLog, Holding, IdempotencyRecord, Loan, Reservation
from app.services import circulation
from app.services.seed import DEFAULT_AS_OF, DEMO_PASSWORD, seed_database


@pytest.fixture
def circulation_app(tmp_path, monkeypatch):
    monkeypatch.setattr(circulation, "utc_now", lambda: DEFAULT_AS_OF + timedelta(hours=12))
    app = create_app(Settings(_env_file=None, environment="test", database_url=f"sqlite:///{tmp_path / 'circulation.db'}"))
    app.state.database.initialize()
    seed_database(app.state.database)
    return app


@pytest.fixture
def client(circulation_app):
    with TestClient(circulation_app) as instance:
        yield instance


def headers(client, number=1, key="test-operation"):
    email = f"student{number}@library.example" if number != 3 else "librarian@library.example"
    response = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["access_token"], "Idempotency-Key": key}


def reserve(client, resource="res-011", auth=None):
    return client.post("/api/v1/reservations", json={"resource_id": resource}, headers=auth or headers(client))


def renew(client, loan="loan-001", auth=None, **kwargs):
    return client.post(f"/api/v1/loans/{loan}/renew", headers=auth or headers(client), **kwargs)


def error(response, status, code):
    assert response.status_code == status
    assert response.json()["status"] == "error"
    assert response.json()["error"]["code"] == code
    assert response.json()["trace_id"] == response.headers["x-trace-id"]


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_personal_lists_cannot_select_another_account(client):
    first = headers(client)
    second = headers(client, 2)
    loans = client.get("/api/v1/me/loans?user_id=user-002", headers=first)
    assert loans.status_code == 200 and loans.headers["cache-control"] == "no-store"
    data = loans.json()["data"]["items"]
    assert {loan["loan_id"] for loan in data} == {"loan-001", "loan-002", "loan-005"}
    by_id = {loan["loan_id"]: loan for loan in data}
    assert by_id["loan-001"]["renewable"] is True
    assert by_id["loan-002"]["status"] == "overdue" and by_id["loan-002"]["fine_amount"] == "1.5"
    assert by_id["loan-005"]["status"] == "returned" and not by_id["loan-005"]["renewable"]
    assert {loan["loan_id"] for loan in client.get("/api/v1/me/loans", headers=second).json()["data"]["items"]} == {"loan-003", "loan-004", "loan-006"}
    reservations = client.get("/api/v1/me/reservations?user_id=user-002", headers=first).json()["data"]["items"]
    assert {r["reservation_id"] for r in reservations} == {"reservation-001", "reservation-005", "reservation-006"}


@pytest.mark.parametrize("path,method", [("/api/v1/me/loans", "get"), ("/api/v1/me/reservations", "get"),
                                       ("/api/v1/reservations", "post"), ("/api/v1/loans/loan-001/renew", "post")])
def test_circulation_requires_authentication(client, path, method):
    response = getattr(client, method)(path, headers={"Idempotency-Key": "key"},
                                       **({"json": {"resource_id": "res-011"}} if path.endswith("/reservations") and method == "post" else {}))
    error(response, 401, "unauthorized")


def test_reservation_allocates_copy_and_replays_without_duplicate_effect(client, circulation_app):
    auth = headers(client)
    first = reserve(client, auth=auth)
    second = reserve(client, auth=auth)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"] == second.json()["data"]
    assert first.json()["data"]["status"] == "active" and first.json()["data"]["queue_position"] is None
    assert first.headers["idempotency-replayed"] == "false" and second.headers["idempotency-replayed"] == "true"
    assert first.json()["trace_id"] != second.json()["trace_id"]
    with circulation_app.state.database.session() as session:
        assert session.get(Holding, "hold-011").available_copies == 2
        assert count(session, Reservation) == 7 and count(session, IdempotencyRecord) == 1
        for response, result in [(first, "success"), (second, "replayed")]:
            log = session.scalar(select(AuditLog).where(AuditLog.trace_id == response.json()["trace_id"]))
            assert log.result == result and log.user_id == "user-001"


def test_duplicate_new_key_and_reused_key_different_payload_conflict(client, circulation_app):
    auth = headers(client)
    assert reserve(client, auth=auth).status_code == 201
    error(reserve(client, auth={**auth, "Idempotency-Key": "another-key"}), 409, "duplicate_reservation")
    error(reserve(client, resource="res-012", auth=auth), 409, "idempotency_conflict")
    with circulation_app.state.database.session() as session:
        assert session.get(Holding, "hold-012").available_copies == 3
        assert count(session, IdempotencyRecord) == 1


def test_same_key_is_independent_for_different_users(client, circulation_app):
    first = reserve(client, auth=headers(client, 1, "shared-key"))
    second = reserve(client, auth=headers(client, 2, "shared-key"))
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["reservation_id"] != second.json()["data"]["reservation_id"]
    with circulation_app.state.database.session() as session:
        assert count(session, IdempotencyRecord) == 2


def test_unavailable_resource_joins_fifo_waitlist(client):
    response = reserve(client, resource="res-002")
    assert response.status_code == 201
    assert response.json()["data"]["status"] == "waitlisted"
    assert response.json()["data"]["queue_position"] == 3
    assert client.get("/api/v1/resources/res-002/availability").json()["data"]["waitlist_count"] == 3


@pytest.mark.parametrize("free,promoted,remaining_position,new_position", [(1, 1, 1, 2), (2, 2, None, 1)])
def test_existing_waiters_get_priority_and_positions_advance(client, circulation_app, free, promoted, remaining_position, new_position):
    with circulation_app.state.database.write_session() as session:
        holding = session.get(Holding, "hold-002")
        holding.total_copies += free
        holding.available_copies = free
    response = reserve(client, resource="res-002")
    assert response.status_code == 201 and response.json()["data"]["queue_position"] == new_position
    with circulation_app.state.database.session() as session:
        assert session.get(Reservation, "reservation-002").status == "active"
        other = session.get(Reservation, "reservation-003")
        assert other.queue_position == remaining_position
        assert other.status == ("active" if promoted == 2 else "waitlisted")
        assert session.get(Holding, "hold-002").available_copies == 0
        logs = list(session.scalars(select(AuditLog).where(AuditLog.trace_id == response.json()["trace_id"], AuditLog.action == "circulation.waitlist_promote")))
        assert len(logs) == promoted


def test_no_holdings_waitlists_and_missing_resource_does_not_consume_key(client, circulation_app):
    auth = headers(client)
    error(reserve(client, resource="missing", auth=auth), 404, "not_found")
    with circulation_app.state.database.session() as session:
        assert count(session, IdempotencyRecord) == 0
    with circulation_app.state.database.write_session() as session:
        holding = session.get(Holding, "hold-011")
        session.delete(holding)
    response = reserve(client, auth=auth)
    assert response.status_code == 201 and response.json()["data"]["status"] == "waitlisted"


@pytest.mark.parametrize("key", [None, "", " ", "contains space", "x" * 129])
def test_idempotency_key_validation(client, key):
    auth = headers(client)
    if key is None:
        auth.pop("Idempotency-Key")
    else:
        auth["Idempotency-Key"] = key
    error(reserve(client, auth=auth), 422, "validation_error")
    error(renew(client, auth=auth), 422, "validation_error")


def test_renewal_extends_once_and_replay_survives_later_state_changes(client, circulation_app, monkeypatch):
    auth = headers(client)
    first = renew(client, auth=auth)
    assert first.status_code == 200
    assert datetime.fromisoformat(first.json()["data"]["due_at"]) == DEFAULT_AS_OF + timedelta(days=21)
    monkeypatch.setattr(circulation, "utc_now", lambda: DEFAULT_AS_OF + timedelta(days=30))
    second = renew(client, auth=auth)
    assert second.status_code == 200 and second.json()["data"] == first.json()["data"]
    assert second.headers["idempotency-replayed"] == "true"
    with circulation_app.state.database.session() as session:
        assert session.get(Loan, "loan-001").renewal_count == 1
    loans = client.get("/api/v1/me/loans", headers=auth).json()["data"]["items"]
    current = next(loan for loan in loans if loan["loan_id"] == "loan-001")
    assert current["status"] == "overdue" and current["renewable"] is False


def test_renewal_limit_and_returned_overdue_cases(client, circulation_app):
    auth = headers(client)
    for number in [1, 2]:
        response = renew(client, auth={**auth, "Idempotency-Key": f"renew-{number}"})
        assert response.status_code == 200
    assert response.json()["data"]["renewable"] is False
    error(renew(client, auth={**auth, "Idempotency-Key": "renew-3"}), 409, "renewal_not_allowed")
    error(renew(client, loan="loan-002", auth=auth), 409, "renewal_not_allowed")
    error(renew(client, loan="loan-005", auth=auth), 409, "renewal_not_allowed")
    with circulation_app.state.database.session() as session:
        loan = session.get(Loan, "loan-001")
        assert loan.renewal_count == 2 and loan.due_at == DEFAULT_AS_OF + timedelta(days=35)


@pytest.mark.parametrize("blocker", ["fine", "due_now", "waitlist", "active_hold"])
def test_eligibility_matches_loan_listing_and_failed_key_can_retry(client, circulation_app, blocker):
    auth = headers(client)
    with circulation_app.state.database.write_session() as session:
        loan = session.get(Loan, "loan-001")
        if blocker == "fine":
            loan.fine_amount_minor = 1
        elif blocker == "due_now":
            loan.due_at = DEFAULT_AS_OF + timedelta(hours=12)
        else:
            session.add(Reservation(reservation_id="blocking", user_id="user-002", resource_id="res-001",
                                    status="active" if blocker == "active_hold" else "waitlisted",
                                    queue_position=None if blocker == "active_hold" else 1,
                                    allocated_holding_id="hold-001" if blocker == "active_hold" else None))
            if blocker == "active_hold":
                session.get(Holding, "hold-001").available_copies -= 1
    response = renew(client, auth=auth)
    error(response, 409, "renewal_not_allowed")
    with circulation_app.state.database.session() as session:
        assert count(session, IdempotencyRecord) == 0 and session.get(Loan, "loan-001").renewal_count == 0
    loan = next(item for item in client.get("/api/v1/me/loans", headers=auth).json()["data"]["items"] if item["loan_id"] == "loan-001")
    assert loan["renewable"] is False
    with circulation_app.state.database.write_session() as session:
        loan = session.get(Loan, "loan-001")
        loan.fine_amount_minor = 0
        loan.due_at = DEFAULT_AS_OF + timedelta(days=7)
        reservation = session.get(Reservation, "blocking")
        if reservation:
            if reservation.allocated_holding_id:
                session.get(Holding, reservation.allocated_holding_id).available_copies += 1
            reservation.status = "cancelled"
            reservation.queue_position = None
            reservation.allocated_holding_id = None
    assert renew(client, auth=auth).status_code == 200


def test_non_owner_and_librarian_cannot_renew_someone_elses_loan(client):
    for number in [2, 3]:
        error(renew(client, auth=headers(client, number)), 403, "forbidden")
    error(renew(client, loan="missing"), 404, "not_found")


@pytest.mark.parametrize("body", [{"days": 999}, {"user_id": "user-002"}, {"role": "librarian"}])
def test_mutations_reject_client_authorization_and_renewal_parameters(client, body):
    error(renew(client, json=body), 422, "validation_error")
    error(client.post("/api/v1/reservations", headers=headers(client), json={"resource_id": "res-011", **body}), 422, "validation_error")


def test_idempotency_is_persistent_across_application_instances(client, circulation_app):
    auth = headers(client)
    first = reserve(client, auth=auth)
    settings = circulation_app.state.settings
    second_app = create_app(Settings(_env_file=None, environment="test", database_url=settings.database_url, jwt_secret=settings.jwt_secret))
    with TestClient(second_app) as second_client:
        replay = reserve(second_client, auth=auth)
    assert replay.status_code == 201 and replay.headers["idempotency-replayed"] == "true"
    assert replay.json()["data"] == first.json()["data"]


def parallel_requests(functions):
    barrier = Barrier(len(functions))
    def run(function):
        barrier.wait(timeout=5)
        return function()
    with ThreadPoolExecutor(max_workers=len(functions)) as executor:
        return list(executor.map(run, functions))


def test_competing_last_copy_reservations_do_not_overbook(client, circulation_app):
    with circulation_app.state.database.write_session() as session:
        holding = session.get(Holding, "hold-011")
        holding.total_copies = holding.available_copies = 1
    one, two = headers(client, 1, "one"), headers(client, 2, "two")
    results = parallel_requests([lambda: reserve(client, auth=one), lambda: reserve(client, auth=two)])
    assert [r.status_code for r in results] == [201, 201]
    assert {r.json()["data"]["status"] for r in results} == {"active", "waitlisted"}
    with circulation_app.state.database.session() as session:
        assert session.get(Holding, "hold-011").available_copies == 0
        assert count(session, IdempotencyRecord) == 2


def test_competing_same_key_reservation_is_one_effect(client, circulation_app):
    auth = headers(client)
    results = parallel_requests([lambda: reserve(client, auth=auth), lambda: reserve(client, auth=auth)])
    assert all(r.status_code == 201 for r in results)
    assert results[0].json()["data"] == results[1].json()["data"]
    assert {r.headers["idempotency-replayed"] for r in results} == {"true", "false"}
    with circulation_app.state.database.session() as session:
        assert session.get(Holding, "hold-011").available_copies == 2
        assert count(session, IdempotencyRecord) == 1


def test_competing_same_key_renewal_extends_only_once(client, circulation_app):
    auth = headers(client)
    results = parallel_requests([lambda: renew(client, auth=auth), lambda: renew(client, auth=auth)])
    assert all(r.status_code == 200 for r in results)
    assert results[0].json()["data"] == results[1].json()["data"]
    with circulation_app.state.database.session() as session:
        assert session.get(Loan, "loan-001").renewal_count == 1


def test_competing_distinct_renewals_cannot_exceed_limit(client, circulation_app):
    with circulation_app.state.database.write_session() as session:
        session.get(Loan, "loan-001").renewal_count = 1
    one, two = headers(client, key="one"), headers(client, key="two")
    results = parallel_requests([lambda: renew(client, auth=one), lambda: renew(client, auth=two)])
    assert sorted(r.status_code for r in results) == [200, 409]
    with circulation_app.state.database.session() as session:
        assert session.get(Loan, "loan-001").renewal_count == 2


@pytest.mark.parametrize("failure_point", ["idempotency", "audit"])
def test_persistence_failures_roll_back_inventory_and_results(client, circulation_app, monkeypatch, failure_point):
    from app.repositories.library import AuditRepository, IdempotencyRepository
    auth = headers(client)
    def fail(self, value):
        raise RuntimeError("simulated persistence failure")
    monkeypatch.setattr(IdempotencyRepository if failure_point == "idempotency" else AuditRepository, "add", fail)
    error(reserve(client, auth=auth), 500, "internal_error")
    with circulation_app.state.database.session() as session:
        assert session.get(Holding, "hold-011").available_copies == 3
        assert count(session, IdempotencyRecord) == 0 and count(session, Reservation) == 6


def test_expected_failure_after_promotion_rolls_back_promotions_but_audits_failure(client, circulation_app, monkeypatch):
    with circulation_app.state.database.write_session() as session:
        holding = session.get(Holding, "hold-002")
        holding.total_copies = 2
        holding.available_copies = 1
    promote = circulation.CirculationService._promote_waitlist
    def fail_after_promotion(self, *args):
        promote(self, *args)
        raise APIError(409, "simulated_conflict", "Simulated business conflict")
    monkeypatch.setattr(circulation.CirculationService, "_promote_waitlist", fail_after_promotion)
    response = reserve(client, resource="res-002")
    error(response, 409, "simulated_conflict")
    with circulation_app.state.database.session() as session:
        assert session.get(Holding, "hold-002").available_copies == 1
        assert session.get(Reservation, "reservation-002").status == "waitlisted"
        assert count(session, IdempotencyRecord) == 0
        logs = list(session.scalars(select(AuditLog).where(AuditLog.trace_id == response.json()["trace_id"])))
        assert len(logs) == 1 and logs[0].result == "conflict"


def test_busy_writer_returns_retryable_conflict(client, circulation_app, monkeypatch):
    @contextmanager
    def locked():
        original = sqlite3.OperationalError("database is locked")
        original.sqlite_errorcode = sqlite3.SQLITE_BUSY
        raise OperationalError("BEGIN IMMEDIATE", {}, original)
        yield
    auth = headers(client)
    monkeypatch.setattr(circulation_app.state.database, "write_session", locked)
    error(reserve(client, auth=auth), 409, "database_busy")


def test_cors_exposes_idempotency_replay_status(client):
    auth = {**headers(client), "Origin": "http://localhost:5173"}
    response = reserve(client, auth=auth)
    assert response.status_code == 201
    assert "Idempotency-Replayed" in response.headers["access-control-expose-headers"]


def test_concurrent_waitlist_entries_get_distinct_positions(client, circulation_app):
    with circulation_app.state.database.write_session() as session:
        holding = session.get(Holding, "hold-011")
        holding.total_copies = holding.available_copies = 0
    one, two = headers(client, 1, "one"), headers(client, 2, "two")
    results = parallel_requests([lambda: reserve(client, auth=one), lambda: reserve(client, auth=two)])
    assert all(r.status_code == 201 and r.json()["data"]["status"] == "waitlisted" for r in results)
    assert {r.json()["data"]["queue_position"] for r in results} == {1, 2}


def test_same_key_can_be_used_for_distinct_operations_and_loan_targets(client, circulation_app):
    auth = headers(client)
    with circulation_app.state.database.write_session() as session:
        session.add(Loan(loan_id="extra-owned", user_id="user-001", resource_id="res-012", holding_id="hold-012",
                         borrowed_at=DEFAULT_AS_OF - timedelta(days=1), due_at=DEFAULT_AS_OF + timedelta(days=5),
                         status="active", renewal_count=0, fine_amount_minor=0))
        session.get(Holding, "hold-012").available_copies -= 1
    assert reserve(client, auth=auth).status_code == 201
    assert renew(client, auth=auth).status_code == 200
    assert renew(client, loan="extra-owned", auth=auth).status_code == 200
    with circulation_app.state.database.session() as session:
        assert count(session, IdempotencyRecord) == 3


def test_replay_rechecks_current_loan_ownership(client, circulation_app):
    auth = headers(client)
    assert renew(client, auth=auth).status_code == 200
    with circulation_app.state.database.write_session() as session:
        session.get(Loan, "loan-001").user_id = "user-002"
    error(renew(client, auth=auth), 403, "forbidden")


@pytest.mark.parametrize("content", ["{}", "null"])
def test_empty_or_null_renewal_body_is_accepted(client, content):
    auth = {**headers(client), "Content-Type": "application/json"}
    assert renew(client, auth=auth, content=content).status_code == 200


def test_own_and_closed_other_holds_do_not_block_renewal(client, circulation_app):
    with circulation_app.state.database.write_session() as session:
        session.add(Reservation(user_id="user-001", resource_id="res-001", status="active",
                                queue_position=None, allocated_holding_id="hold-001"))
        session.get(Holding, "hold-001").available_copies -= 1
        session.add(Reservation(user_id="user-002", resource_id="res-001", status="cancelled",
                                queue_position=None, allocated_holding_id=None))
    assert renew(client).status_code == 200


def test_renewal_audit_failure_rolls_back_due_date_count_and_result(client, circulation_app, monkeypatch):
    from app.repositories.library import AuditRepository
    auth = headers(client)
    def fail(self, record):
        raise RuntimeError("simulated audit failure")
    monkeypatch.setattr(AuditRepository, "add", fail)
    error(renew(client, auth=auth), 500, "internal_error")
    with circulation_app.state.database.session() as session:
        loan = session.get(Loan, "loan-001")
        assert loan.due_at == DEFAULT_AS_OF + timedelta(days=7) and loan.renewal_count == 0
        assert count(session, IdempotencyRecord) == 0
