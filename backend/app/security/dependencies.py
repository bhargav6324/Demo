from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models import User
from app.repositories.library import UserRepository
from app.security.tokens import TokenService, unauthorized

bearer = HTTPBearer(auto_error=False, description="JWT access token from POST /api/v1/auth/login.")
DatabaseSession = Annotated[Session, Depends(get_session)]


def get_optional_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User | None:
    if credentials is None:
        if request.headers.get("Authorization") is not None:
            raise unauthorized("Bearer authentication is required")
        return None
    if len(credentials.credentials) > 8192:
        raise unauthorized()
    subject = TokenService(request.app.state.settings).subject(credentials.credentials)
    # Close the read transaction before a route starts a write/audit transaction.
    # Profile is eagerly loaded by the repository, so the returned identity is usable.
    with request.app.state.database.session() as session:
        user = UserRepository(session).get(subject)
    if user is None:
        raise unauthorized()
    request.state.audit_user_id = user.user_id
    return user


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise unauthorized("Bearer authentication is required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
