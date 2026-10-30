"""Circulation policy from the backend handoff (latest: 2026-10-30).

Used only for previews and wording; the backend remains the authority and
enforces these rules itself."""
from app.schemas.library import Role

# Only patrons reserve and renew; librarians administer (backend returns 403)
PATRON_ROLES: set[Role] = {"student", "faculty", "researcher"}

# Waitlist priority: faculty, then researcher, then student; FIFO within a role
QUEUE_RANK: dict[str, int] = {"faculty": 0, "researcher": 1, "student": 2}

_RENEWAL_DAYS = {"faculty": 28}
DEFAULT_RENEWAL_DAYS = 14  # students and researchers


def renewal_days(role: str) -> int:
    return _RENEWAL_DAYS.get(role, DEFAULT_RENEWAL_DAYS)
