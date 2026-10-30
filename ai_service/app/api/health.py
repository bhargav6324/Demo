from fastapi import APIRouter, Depends

from app.api.deps import get_services
from app.schemas.envelope import SuccessEnvelope
from app.services import Services

router = APIRouter(tags=["health"])


@router.get("/health", response_model=SuccessEnvelope)
async def health(services: Services = Depends(get_services)) -> SuccessEnvelope:
    s = services.settings
    backend_ok = await services.adapter.health()
    llm_ok = services.orchestrator is not None
    return SuccessEnvelope(
        data={
            # ok: chat fully works | degraded: running, but backend or LLM unavailable
            "status": "ok" if backend_ok and llm_ok else "degraded",
            "service": "smart-library-ai",
            "tool_adapter": s.tool_adapter,
            "backend_reachable": backend_ok,
            "llm_provider": s.llm_provider,
            "llm_model": s.llm_model,
            "llm_ready": llm_ok,
            "tools": services.executor.registry.names(),
            "embedder": services.retriever.embedder.name,
            "indexed_chunks": len(services.retriever.store) if services.retriever.store else 0,
        }
    )
