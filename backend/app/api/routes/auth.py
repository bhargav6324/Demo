from fastapi import APIRouter, Request, Response

from app.schemas.common import SuccessResponse
from app.schemas.domain import LoginData, LoginRequest, Profile, UserIdentity
from app.security.dependencies import CurrentUser, DatabaseSession
from app.security.tokens import TokenService
from app.services.auth import AuthService, identity_data, profile_data

router = APIRouter()


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post("/auth/login", response_model=SuccessResponse[LoginData], tags=["authentication"], operation_id="login")
def login(body: LoginRequest, request: Request, response: Response, session: DatabaseSession):
    """Verify email/password and issue a short-lived JWT access token."""
    data = AuthService(session, TokenService(request.app.state.settings)).login(body.email, body.password.get_secret_value())
    request.state.audit_user_id = data.user.user_id
    private_response(response)
    return SuccessResponse(data=data, trace_id=request.state.trace_id)


@router.get("/auth/me", response_model=SuccessResponse[UserIdentity], tags=["authentication"], operation_id="get_current_user")
def current_user(request: Request, response: Response, user: CurrentUser):
    """Return identity from the verified JWT subject and current database record."""
    private_response(response)
    return SuccessResponse(data=identity_data(user), trace_id=request.state.trace_id)


@router.get("/me/profile", response_model=SuccessResponse[Profile], tags=["profile"], operation_id="get_profile")
def profile(request: Request, response: Response, user: CurrentUser):
    """Return only the authenticated user's courses and interests."""
    private_response(response)
    return SuccessResponse(data=profile_data(user), trace_id=request.state.trace_id)
