"""Reusable checks; ownership IDs must come from trusted database records."""

from fastapi import HTTPException

from app.models import User
from app.security.dependencies import CurrentUser


def require_librarian(user: CurrentUser) -> User:
    if user.role != "librarian":
        raise HTTPException(403, "Librarian permission is required")
    return user


def require_owner(user: User, owner_user_id: str) -> None:
    # No implicit librarian bypass for a patron's private account operations.
    if user.user_id != owner_user_id:
        raise HTTPException(403, "Access to another user's data is forbidden")
