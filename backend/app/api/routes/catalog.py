from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.schemas.common import StableID, SuccessResponse, UTCTimestamp
from app.schemas.domain import (
    Availability, Level, Resource, ResourceContent, ResourceCreate, ResourceList, ResourcePatch, ResourceType,
)
from app.security.dependencies import CurrentUser, OptionalUser
from app.services.catalog import CatalogService

router = APIRouter(prefix="/resources", tags=["catalog"])


def catalog(request: Request) -> CatalogService:
    return CatalogService(request.app.state.database)


def result(data, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return SuccessResponse(data=data, trace_id=request.state.trace_id)


@router.get("", response_model=SuccessResponse[ResourceList], operation_id="search_resources")
def search_resources(
    request: Request, response: Response,
    query: Annotated[str | None, Query(max_length=1000)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=2_147_483_647)] = 0,
    type: ResourceType | None = None,
    level: Level | None = None,
    updated_since: UTCTimestamp | None = None,
):
    """Public literal metadata search; total counts matches before offset/limit."""
    data = catalog(request).search(query=query, limit=limit, offset=offset, resource_type=type,
                                   level=level, updated_since=updated_since)
    return result(data, request, response)


@router.get("/{resource_id}", response_model=SuccessResponse[Resource], operation_id="get_resource")
def get_resource(resource_id: StableID, request: Request, response: Response):
    return result(catalog(request).details(resource_id), request, response)


@router.get("/{resource_id}/availability", response_model=SuccessResponse[Availability], operation_id="get_availability")
def get_availability(resource_id: StableID, request: Request, response: Response):
    return result(catalog(request).availability(resource_id), request, response)


@router.get("/{resource_id}/content", response_model=SuccessResponse[ResourceContent], operation_id="get_content",
            openapi_extra={"security": [{}]})
def get_content(resource_id: StableID, request: Request, response: Response, user: OptionalUser):
    """Public: anonymous; authenticated: any user; restricted: librarian only."""
    return result(catalog(request).content(resource_id, user, request.state.trace_id), request, response)


@router.post("", status_code=201, response_model=SuccessResponse[Resource], operation_id="create_resource")
def create_resource(body: ResourceCreate, request: Request, response: Response, user: CurrentUser):
    """Librarian only. Create metadata; holdings and content are not invented."""
    return result(catalog(request).create(body, user, request.state.trace_id), request, response)


@router.patch("/{resource_id}", response_model=SuccessResponse[Resource], operation_id="update_resource")
def update_resource(resource_id: StableID, body: ResourcePatch, request: Request, response: Response, user: CurrentUser):
    """Librarian only. Omit unchanged fields; explicit null/empty patches are invalid."""
    return result(catalog(request).patch(resource_id, body, user, request.state.trace_id), request, response)
