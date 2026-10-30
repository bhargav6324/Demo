"""JWT issuance and verification with a fixed algorithm and application scope."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException

from app.core.config import Settings

ALGORITHM = "HS256"


def unauthorized(message: str = "Invalid or expired access token") -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})


class TokenService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def issue(self, user_id: str) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode({
            "sub": user_id,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=self.settings.jwt_access_token_minutes),
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "type": "access",
            "jti": str(uuid4()),
        }, self.settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)

    def subject(self, token: str) -> str:
        try:
            claims = jwt.decode(
                token,
                self.settings.jwt_secret.get_secret_value(),
                algorithms=[ALGORITHM],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={"require": ["sub", "exp", "iat", "nbf", "iss", "aud", "type", "jti"]},
            )
            if claims["type"] != "access" or not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 128:
                raise unauthorized()
            # Tokens carry identity only; roles and permissions are reloaded from the database.
            return claims["sub"]
        except (jwt.InvalidTokenError, TypeError, ValueError, OverflowError):
            raise unauthorized() from None
