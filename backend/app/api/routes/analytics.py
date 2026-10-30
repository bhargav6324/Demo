from fastapi import APIRouter, Request, Response

from app.schemas.common import SuccessResponse
from app.schemas.domain import AnalyticsSummary
from app.security.dependencies import CurrentUser
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=SuccessResponse[AnalyticsSummary], operation_id="get_analytics_summary")
def summary(request: Request, response: Response, user: CurrentUser):
    """Librarian only: aggregate catalog, outstanding loans, demand, and popular titles."""
    data = AnalyticsService(request.app.state.database).summary(user)
    response.headers["Cache-Control"] = "no-store"
    return SuccessResponse(data=data, trace_id=request.state.trace_id)
