from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from app.schemas.common import StableID, SuccessResponse
from app.schemas.domain import Loan, LoanList, RenewalRequest, Reservation, ReservationCreate, ReservationList
from app.security.dependencies import CurrentUser
from app.services.circulation import CirculationService

router = APIRouter(tags=["circulation"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[!-~]+$")]
REPLAY_HEADERS = {"Idempotency-Replayed": {
    "description": "True when replaying a previously committed result without another effect",
    "schema": {"type": "boolean"},
}}


def result(data, request, response):
    response.headers["Cache-Control"] = "no-store"
    return SuccessResponse(data=data, trace_id=request.state.trace_id)


def mutation_result(outcome, request, response):
    response.status_code = outcome.status_code
    response.headers["Idempotency-Replayed"] = str(outcome.replayed).lower()
    return result(outcome.data, request, response)


@router.get("/me/loans", response_model=SuccessResponse[LoanList], operation_id="get_my_loans")
def loans(request: Request, response: Response, user: CurrentUser):
    """Return only the caller's loans, including returned history and current eligibility."""
    return result(CirculationService(request.app.state.database).loans(user), request, response)


@router.get("/me/reservations", response_model=SuccessResponse[ReservationList], operation_id="get_my_reservations")
def reservations(request: Request, response: Response, user: CurrentUser):
    return result(CirculationService(request.app.state.database).reservations(user), request, response)


@router.post("/reservations", status_code=201, response_model=SuccessResponse[Reservation],
             operation_id="create_reservation", responses={201: {"headers": REPLAY_HEADERS}})
def reserve(body: ReservationCreate, key: IdempotencyKey, request: Request, response: Response, user: CurrentUser):
    """Allocate a free copy or join the FIFO waitlist; retries replay the committed result."""
    outcome = CirculationService(request.app.state.database).reserve(body, user, key, request.state.trace_id)
    return mutation_result(outcome, request, response)


@router.post("/loans/{loan_id}/renew", response_model=SuccessResponse[Loan],
             operation_id="renew_loan", responses={200: {"headers": REPLAY_HEADERS}})
def renew(loan_id: StableID, key: IdempotencyKey, request: Request, response: Response,
          user: CurrentUser, body: RenewalRequest | None = None):
    """Owner only: add 14 days, at most twice, subject to due/fine/hold checks."""
    outcome = CirculationService(request.app.state.database).renew(loan_id, user, key, request.state.trace_id)
    return mutation_result(outcome, request, response)
