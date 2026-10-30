"""Documentation-only API. This router is never mounted on the running app."""

from fastapi import APIRouter, Depends

from app.core.errors import APIError
from app.main import create_app
from app.security.dependencies import bearer
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.domain import AnalyticsSummary

protected = APIRouter(dependencies=[Depends(bearer)])
public = APIRouter()


def not_implemented():
    raise APIError(501, "not_implemented", "Draft contract only; endpoint is not implemented")


@protected.get("/analytics/summary", response_model=SuccessResponse[AnalyticsSummary], tags=["analytics"], description="Librarian only.")
def analytics():
    not_implemented()


def create_contract_app():
    app = create_app()
    app.title = "Smart Library Backend - DRAFT contract"
    app.description = (
        "Contract for all 15 operations. Health, authentication, profile, catalog, and circulation are implemented. "
        "Remaining routes are documentation-only and are not mounted in the runtime app. "
        "Access-policy defaults and proposed fields are detailed in docs/API_CONTRACT.md."
    )
    for router in (public, protected):
        app.include_router(router, prefix="/api/v1", responses={501: {"model": ErrorResponse}})
    return app
