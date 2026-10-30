from fastapi import Header, HTTPException, Request

from app.adapters.errors import ToolError
from app.auth.context import UserContext
from app.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


async def get_optional_user(request: Request, authorization: str | None = Header(default=None)) -> UserContext | None:
    """Anonymous callers may search the catalog; a present-but-invalid token is a 401."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Authorization header must be 'Bearer <token>'.")
    try:
        return await get_services(request).identity.authenticate(token.strip())
    except ToolError as e:
        if e.code == ToolError.UNAUTHORIZED:
            raise HTTPException(status_code=401, detail=e.message) from e
        raise HTTPException(status_code=503, detail="Identity service unavailable.") from e
