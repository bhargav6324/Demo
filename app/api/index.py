from fastapi import APIRouter, Depends, HTTPException

from app.adapters.errors import ToolError
from app.api.deps import get_optional_user, get_services
from app.auth.context import UserContext
from app.schemas.envelope import SuccessEnvelope
from app.services import Services

router = APIRouter(prefix="/index", tags=["index"])


@router.post("/refresh")
async def refresh_index(full: bool = False, user: UserContext | None = Depends(get_optional_user),
                        services: Services = Depends(get_services)):
    """Librarian-only: pull resources changed since the last refresh into the vector index."""
    if user is None or not user.is_librarian:
        raise HTTPException(status_code=403, detail="Index refresh is restricted to librarians.")
    try:
        stats = await services.retriever.refresh(full=full)
    except ToolError as e:
        raise HTTPException(status_code=503, detail=f"Backend unavailable: {e.message}") from e
    return SuccessEnvelope(data=stats)
