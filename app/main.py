import asyncio
import contextlib
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import chat, health, index
from app.config import get_settings
from app.schemas.envelope import ErrorBody, ErrorEnvelope
from app.services import Services, build_services

API_PREFIX = "/api/v1"
logger = logging.getLogger("smartlibrary")


async def _refresh_loop(services: Services, interval: int) -> None:
    """Keep the vector index fresh: new/updated backend resources become
    searchable without code changes or restarts."""
    while True:
        try:
            await services.retriever.refresh()
        except Exception as e:  # noqa: BLE001 - backend may be down; retry next tick
            logger.warning("Index refresh failed: %s", e)
        await asyncio.sleep(interval)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    services: Services = app.state.services
    interval = services.settings.rag_refresh_seconds
    task = asyncio.create_task(_refresh_loop(services, interval)) if interval > 0 else None
    yield
    if task:
        task.cancel()
    if hasattr(services.adapter, "aclose"):
        await services.adapter.aclose()


def create_app(services: Services | None = None) -> FastAPI:
    settings = services.settings if services else get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(title="Smart Library AI Service", version="0.1.0", lifespan=lifespan)
    app.state.services = services or build_services(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    app.include_router(index.router, prefix=API_PREFIX)

    # Every error leaves the service in the standard error envelope.
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        body = ErrorEnvelope(error=ErrorBody(code=f"http_{exc.status_code}", message=str(exc.detail)))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        body = ErrorEnvelope(error=ErrorBody(code="invalid_request", message=str(exc.errors())))
        return JSONResponse(status_code=422, content=body.model_dump())

    return app


app = create_app()
