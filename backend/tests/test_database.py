from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, StatementError

from app.core.database import Database
from app.models import AuditLog, Base, Holding, IdempotencyRecord, Loan, Reservation, Resource, User
from app.repositories.library import CirculationRepository, HoldingRepository, IdempotencyRepository, ResourceRepository, UserRepository
from app.security.passwords import hash_password, verify_password
from app.services.seed import DEFAULT_AS_OF, DEMO_PASSWORD, seed_database
from scripts.database import main as database_command


@pytest.fixture
def database(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'library.db'}")
    db.initialize()
    yield db
    db.dispose()


@pytest.fixture
def seeded(database):
    assert seed_database(database)
    return database


def snapshot(db):
    with db.session() as session:
        result = {}
        for table in Base.metadata.sorted_tables:
            rows = session.execute(select(table).order_by(*table.primary_key.columns)).mappings().all()
            result[table.name] = [{k: v for k, v in row.items() if k != "password_hash"} for row in rows]
        return result


def test_schema_has_required_tables_foreign_keys_and_indexes(database):
    inspector = inspect(database.engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables)
    assert len(inspector.get_table_names()) == 9
    assert inspector.get_foreign_keys("loans")
    assert {i["name"] for i in inspector.get_indexes("reservations")} >= {
        "uq_reservations_open_user_resource", "uq_reservations_waitlist_position"
    }
    with database.session() as session:
        assert session.scalar(text("PRAGMA foreign_keys")) == 1
        assert session.scalar(text("PRAGMA busy_timeout")) == 5000
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []


def test_seed_counts_profiles_types_and_inventory_balance(seeded):
    with seeded.session() as session:
        assert session.scalar(select(func.count()).select_from(Resource)) == 30
        assert session.scalar(select(func.count()).select_from(User)) == 3
        assert session.scalar(select(func.count()).select_from(Holding)) == 33
        assert session.scalar(select(func.count()).select_from(Loan)) == 6
        assert session.scalar(select(func.count()).select_from(Reservation)) == 6
        resources = ResourceRepository(session).list()
        assert {r.type for r in resources} == {"book", "journal", "paper", "ebook", "dissertation"}
        assert {r.level for r in resources} == {"beginner", "intermediate", "advanced"}
        assert {r.access_level for r in resources} == {"public", "authenticated", "restricted"}
        assert all(r.content and "Synthetic" in r.content.content for r in resources)
        assert UserRepository(session).get("user-001").profile.courses == ["CS101", "DS201"]
        assert len({h.branch for r in resources for h in r.holdings}) == 3
        for holding in session.scalars(select(Holding)):
            loans = session.scalar(select(func.count()).select_from(Loan).where(
                Loan.holding_id == holding.holding_id, Loan.status.in_(["active", "overdue"])))
            holds = session.scalar(select(func.count()).select_from(Reservation).where(
                Reservation.allocated_holding_id == holding.holding_id, Reservation.status == "active"))
            assert holding.total_copies == holding.available_copies + loans + holds
        assert session.get(Holding, "hold-002").available_copies == 0
        assert session.get(Holding, "hold-009").available_copies == 0
        assert session.get(Loan, "loan-002").due_at < DEFAULT_AS_OF
        assert session.get(Loan, "loan-001").due_at > DEFAULT_AS_OF
        assert session.get(Loan, "loan-002").fine_amount == Decimal("1.50")


def test_seed_is_reproducible_and_rerun_preserves_changes(seeded, tmp_path):
    other = Database(f"sqlite:///{tmp_path / 'other.db'}")
    try:
        other.initialize()
        assert seed_database(other)
        assert snapshot(seeded) == snapshot(other)
    finally:
        other.dispose()
    with seeded.write_session() as session:
        session.get(Resource, "res-001").title = "Changed after seeding"
    before = snapshot(seeded)
    assert seed_database(seeded) is False
    assert snapshot(seeded) == before


def test_seed_refuses_nonempty_unmarked_database(database):
    with database.write_session() as session:
        session.add(Resource(resource_id="custom", title="Custom", authors=["A"], type="book",
                             description="Existing data", topics=[], level="beginner", access_level="public"))
    with pytest.raises(ValueError, match="nonempty"):
        seed_database(database)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Resource)) == 1
        assert session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("statement", [
    "UPDATE holdings SET available_copies = -1 WHERE holding_id = 'hold-001'",
    "UPDATE holdings SET available_copies = total_copies + 1 WHERE holding_id = 'hold-001'",
    "UPDATE holdings SET total_copies = -1 WHERE holding_id = 'hold-001'",
    "UPDATE loans SET user_id = 'missing' WHERE loan_id = 'loan-001'",
    "UPDATE loans SET holding_id = 'hold-002' WHERE loan_id = 'loan-001'",
    "UPDATE loans SET fine_amount_minor = -1 WHERE loan_id = 'loan-001'",
    "UPDATE loans SET status = 'returned' WHERE loan_id = 'loan-001'",
    "UPDATE loans SET due_at = '2000-01-01' WHERE loan_id = 'loan-001'",
    "UPDATE resources SET type = 'invalid' WHERE resource_id = 'res-001'",
    "UPDATE users SET email = 'student1@library.example' WHERE user_id = 'user-002'",
    "UPDATE reservations SET queue_position = 0 WHERE reservation_id = 'reservation-002'",
    "UPDATE reservations SET queue_position = 1 WHERE reservation_id = 'reservation-003'",
    "UPDATE reservations SET user_id = 'user-002' WHERE reservation_id = 'reservation-003'",
    "DELETE FROM users WHERE user_id = 'user-001'",
])
def test_database_rejects_invalid_relationships_inventory_and_statuses(seeded, statement):
    with pytest.raises(IntegrityError):
        with seeded.write_session() as session:
            session.execute(text(statement))


def test_write_transaction_rolls_back_all_changes(seeded):
    with pytest.raises(RuntimeError):
        with seeded.write_session() as session:
            assert HoldingRepository(session).try_allocate("hold-001")
            session.add(AuditLog(audit_id="must-rollback", user_id="user-001", action="test", result="success", trace_id="test"))
            session.flush()
            raise RuntimeError("simulated workflow failure")
    with seeded.session() as session:
        assert session.get(Holding, "hold-001").available_copies == 2
        assert session.get(AuditLog, "must-rollback") is None


def test_competing_allocations_cannot_take_the_last_copy_twice(seeded):
    with seeded.write_session() as session:
        # Resource 6 has one active allocated hold, leaving two free copies originally.
        session.get(Holding, "hold-006").available_copies = 1
    barrier = Barrier(2)

    def allocate():
        barrier.wait(timeout=5)
        with seeded.write_session() as session:
            return HoldingRepository(session).try_allocate("hold-006")

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: allocate(), range(2)))
    assert sorted(outcomes) == [False, True]
    with seeded.session() as session:
        assert session.get(Holding, "hold-006").available_copies == 0


def test_idempotency_records_are_persistent_and_scoped(seeded):
    def record(user="user-001", operation="POST /reservations", digest="a" * 64):
        return IdempotencyRecord(user_id=user, operation=operation, key="demo-key", request_hash=digest,
                                 status_code=201, response_data={"reservation_id": "reservation-001"})
    with seeded.write_session() as session:
        repo = IdempotencyRepository(session)
        repo.add(record())
        repo.add(record(user="user-002"))
        repo.add(record(operation="POST /loans/loan-001/renew"))
    with seeded.session() as session:
        found = IdempotencyRepository(session).get("user-001", "POST /reservations", "demo-key")
        assert found.response_data == {"reservation_id": "reservation-001"}
        assert found.request_hash == "a" * 64
    with pytest.raises(IntegrityError):
        with seeded.write_session() as session:
            IdempotencyRepository(session).add(record(digest="b" * 64))


def test_repository_lookup_normalization_and_user_scoping(seeded):
    with seeded.session() as session:
        assert UserRepository(session).by_email(" STUDENT1@LIBRARY.EXAMPLE ").user_id == "user-001"
        circulation = CirculationRepository(session)
        assert {loan.user_id for loan in circulation.loans_for_user("user-001")} == {"user-001"}
        assert circulation.loan_for_user("loan-001", "user-002") is None
        assert {r.user_id for r in circulation.reservations_for_user("user-002")} == {"user-002"}


def test_passwords_are_salted_and_verifiable(seeded):
    with seeded.session() as session:
        users = list(session.scalars(select(User)))
        assert len({u.password_hash for u in users}) == 3
        for user in users:
            assert DEMO_PASSWORD not in user.password_hash
            assert verify_password(DEMO_PASSWORD, user.password_hash)
            assert not verify_password("incorrect", user.password_hash)
    assert not verify_password(DEMO_PASSWORD, "malformed")
    assert not verify_password(DEMO_PASSWORD, "pbkdf2_sha256$600000$%%%$%%%")


def test_utc_round_trip_and_resource_update_tracking(seeded):
    original = DEFAULT_AS_OF
    with seeded.write_session() as session:
        resource = session.get(Resource, "res-001")
        resource.title = "Updated fixture title"
    with seeded.session() as session:
        resource = session.get(Resource, "res-001")
        assert resource.updated_at.tzinfo == timezone.utc
        # Ensure tracking changed without depending on the execution host's date.
        assert resource.updated_at != original
    with pytest.raises(StatementError):
        with seeded.write_session() as session:
            session.get(Resource, "res-001").updated_at = original.replace(tzinfo=None)


def test_seed_anchor_date_is_explicit(database):
    anchor = DEFAULT_AS_OF + timedelta(days=30)
    seed_database(database, anchor)
    with database.session() as session:
        assert session.get(Loan, "loan-001").due_at == anchor + timedelta(days=7)
        assert session.get(Loan, "loan-002").due_at < anchor


def test_cli_init_seed_and_guarded_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_ENVIRONMENT", "test")
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    database_command(["--database-url", url, "init"])
    database_command(["--database-url", url, "seed", "--as-of", "2026-10-30"])
    with pytest.raises(SystemExit) as failure:
        database_command(["--database-url", url, "reset"])
    assert failure.value.code == 2
    check = Database(url)
    try:
        with check.session() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 3
        database_command(["--database-url", url, "reset", "--confirm-reset"])
        with check.session() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 0
    finally:
        check.dispose()
    monkeypatch.setenv("LIBRARY_ENVIRONMENT", "production")
    monkeypatch.setenv("LIBRARY_JWT_SECRET", "test-only-production-key-not-a-real-secret-123")
    for command in (["seed"], ["reset", "--confirm-reset"]):
        with pytest.raises(SystemExit):
            database_command(["--database-url", url, *command])


def test_memory_database_and_rolled_back_read_session():
    db = Database("sqlite:///:memory:")
    try:
        db.initialize()
        with db.session() as session:
            session.add(AuditLog(audit_id="not-committed", action="test", result="success", trace_id="test"))
            session.flush()
        with db.session() as session:
            assert session.get(AuditLog, "not-committed") is None
    finally:
        db.dispose()
