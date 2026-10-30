from fastapi import APIRouter, Request

from app.schemas.common import HealthData, SuccessResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=SuccessResponse[HealthData], operation_id="get_health")
def health(request: Request):
    """Process liveness only; database connectivity is added in a later phase."""
    return SuccessResponse(
        data=HealthData(service=request.app.state.settings.app_name, version="0.1.0"),
        trace_id=request.state.trace_id,
    )
