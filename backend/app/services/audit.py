"""Request-level coverage complements existing atomic business audit records."""

from app.core.database import Database
from app.models import AuditLog
from app.repositories.library import AuditRepository, UserRepository


class AuditService:
    def __init__(self, database: Database):
        self.database = database

    def record_request(self, user_id: str | None, action: str, result: str, trace_id: str):
        with self.database.write_session() as session:
            repository = AuditRepository(session)
            if repository.has_trace(trace_id):
                # Catalog/circulation/content already record the authoritative outcome.
                return
            user = UserRepository(session).get(user_id) if user_id else None
            repository.add(AuditLog(
                user_id=user.user_id if user else None,
                action=action, result=result, trace_id=trace_id,
            ))
