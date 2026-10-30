import secrets

from sqlalchemy.orm import Session

from app.models import User
from app.repositories.library import UserRepository
from app.schemas.domain import LoginData, Profile, User as UserSchema, UserIdentity
from app.security.passwords import hash_password, verify_password
from app.security.tokens import TokenService, unauthorized

# Keep the costly verification step for unknown accounts too, without a real credential.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def identity_data(user: User) -> UserIdentity:
    return UserIdentity(user_id=user.user_id, name=user.name, email=user.email, role=user.role)


def profile_data(user: User) -> Profile:
    profile = user.profile
    return Profile(courses=profile.courses if profile else [], interests=profile.interests if profile else [])


class AuthService:
    def __init__(self, session: Session, tokens: TokenService):
        self.users = UserRepository(session)
        self.tokens = tokens

    def login(self, email: str, password: str) -> LoginData:
        user = self.users.by_email(email)
        valid = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
        if not valid or user is None:
            raise unauthorized("Invalid email or password")
        public_user = UserSchema(**identity_data(user).model_dump(), **profile_data(user).model_dump())
        return LoginData(
            access_token=self.tokens.issue(user.user_id),
            expires_in=self.tokens.settings.jwt_access_token_minutes * 60,
            user=public_user,
        )
