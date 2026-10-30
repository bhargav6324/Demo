from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


class Database:
    """Own an engine; repositories flush, while callers own transaction boundaries."""

    def __init__(self, url: str):
        parsed = make_url(url)
        if parsed.drivername not in {"sqlite", "sqlite+pysqlite"}:
            raise ValueError("This hackathon backend currently supports SQLite only")
        options = {"connect_args": {"check_same_thread": False, "timeout": 5}}
        if parsed.database in {None, "", ":memory:"}:
            options["poolclass"] = StaticPool
        self.engine = create_engine(url, **options)

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _):
            # Explicit BEGIN works consistently across Python 3.11+ sqlite drivers.
            connection.isolation_level = None
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        @event.listens_for(self.engine, "begin")
        def begin(connection):
            mode = "IMMEDIATE" if connection.get_execution_options().get("sqlite_write_lock") else "DEFERRED"
            connection.exec_driver_sql(f"BEGIN {mode}")

        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self):
        # Creates missing tables only; does not migrate or reset existing schemas.
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self):
        """Read/unit-of-work session; no automatic commit on exit."""
        with self.sessions() as session:
            yield session

    @contextmanager
    def write_session(self):
        """Serialize read-modify-write operations before their first database read."""
        with self.sessions() as session:
            session.connection(execution_options={"sqlite_write_lock": True})
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def dispose(self):
        self.engine.dispose()


def get_session(request: Request):
    """Future routes may use read sessions; write services use write_session explicitly."""
    with request.app.state.database.session() as session:
        yield session
