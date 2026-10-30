"""Documentation-only API. This router is never mounted on the running app."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.core.errors import APIError
from app.main import create_app
from app.security.dependencies import bearer
from app.schemas.common import ErrorResponse, StableID, SuccessResponse
from app.schemas.domain import (
    AnalyticsSummary, Loan, LoanList, Reservation, ReservationCreate, ReservationList,
)

protected = APIRouter(dependencies=[Depends(bearer)])
public = APIRouter()
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def not_implemented():
    raise APIError(501, "not_implemented", "Draft contract only; endpoint is not implemented")


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
        "Contract for all 15 operations. Health, authentication, profile, and catalog are implemented. "
        "Remaining routes are documentation-only and are not mounted in the runtime app. "
        "Access-policy defaults and proposed fields are detailed in docs/API_CONTRACT.md."
    )
    for router in (public, protected):
        app.include_router(router, prefix="/api/v1", responses={501: {"model": ErrorResponse}})
    return app
