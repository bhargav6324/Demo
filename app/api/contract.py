"""Documentation-only API. This router is never mounted on the running app."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.security import HTTPBearer

from app.core.errors import APIError
from app.main import create_app
from app.schemas.common import ErrorResponse, StableID, SuccessResponse, UTCTimestamp
from app.schemas.domain import (
    AnalyticsSummary, Availability, Level, Loan, LoanList, LoginData, LoginRequest,
    Profile, Reservation, ReservationCreate, ReservationList, Resource, ResourceContent,
    ResourceCreate, ResourceList, ResourcePatch, ResourceType, UserIdentity,
)

bearer = HTTPBearer(description="Planned: verified user JWT. Librarian operations also require role checks.")
protected = APIRouter(dependencies=[Depends(bearer)])
public = APIRouter()
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def not_implemented():
    raise APIError(501, "not_implemented", "Draft contract only; endpoint is not implemented")


@public.post("/auth/login", response_model=SuccessResponse[LoginData], tags=["authentication"])
def login(body: LoginRequest):
    not_implemented()


@protected.get("/auth/me", response_model=SuccessResponse[UserIdentity], tags=["authentication"])
def current_user():
    not_implemented()


@protected.get("/me/profile", response_model=SuccessResponse[Profile], tags=["profile"])
def profile():
    not_implemented()


@public.get("/resources", response_model=SuccessResponse[ResourceList], tags=["catalog"])
def resources(
    query: Annotated[str | None, Query(max_length=1000)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    type: ResourceType | None = None,
    level: Level | None = None,
    updated_since: UTCTimestamp | None = None,
):
    not_implemented()


@public.get("/resources/{resource_id}", response_model=SuccessResponse[Resource], tags=["catalog"])
def resource(resource_id: StableID):
    not_implemented()


@public.get("/resources/{resource_id}/availability", response_model=SuccessResponse[Availability], tags=["catalog"])
def availability(resource_id: StableID):
    not_implemented()


@protected.get("/resources/{resource_id}/content", response_model=SuccessResponse[ResourceContent], tags=["catalog"])
def content(resource_id: StableID):
    not_implemented()


@protected.post("/resources", status_code=201, response_model=SuccessResponse[Resource], tags=["catalog"], description="Librarian only.")
def create_resource(body: ResourceCreate):
    not_implemented()


@protected.patch("/resources/{resource_id}", response_model=SuccessResponse[Resource], tags=["catalog"], description="Librarian only; omit unchanged fields; explicit null is invalid.")
def update_resource(resource_id: StableID, body: ResourcePatch):
    not_implemented()


@protected.get("/me/loans", response_model=SuccessResponse[LoanList], tags=["circulation"])
def loans():
    not_implemented()


@protected.post("/loans/{loan_id}/renew", response_model=SuccessResponse[Loan], tags=["circulation"])
def renew(loan_id: StableID, idempotency_key: IdempotencyKey):
    not_implemented()


@protected.post("/reservations", status_code=201, response_model=SuccessResponse[Reservation], tags=["circulation"])
def reserve(body: ReservationCreate, idempotency_key: IdempotencyKey):
    not_implemented()


@protected.get("/me/reservations", response_model=SuccessResponse[ReservationList], tags=["circulation"])
def reservations():
    not_implemented()


@protected.get("/analytics/summary", response_model=SuccessResponse[AnalyticsSummary], tags=["analytics"], description="Librarian only.")
def analytics():
    not_implemented()


def create_contract_app():
    app = create_app()
    app.title = "Smart Library Backend - DRAFT contract"
    app.description = (
        "Planning contract for all 15 operations. Only health is implemented in Phase 1. "
        "Other routes are documentation-only and are not mounted in the runtime app. "
        "Access-policy defaults and proposed fields are detailed in docs/API_CONTRACT.md."
    )
    for router in (public, protected):
        app.include_router(router, prefix="/api/v1", responses={501: {"model": ErrorResponse}})
    return app
