from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.circulation import router as circulation_router
from app.api.routes.analytics import router as analytics_router
from app.core.audit_middleware import RequestAuditMiddleware
from app.core.config import Settings
from app.core.database import Database
from app.core.errors import register_error_handlers
from app.core.middleware import TraceMiddleware
from app.schemas.common import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            database.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Phase 6 implementation: all 15 required operations, including librarian analytics. Phase 6 awaits independent tester validation.",
        responses={code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 405, 409, 422, 500)},
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    register_error_handlers(app)
    app.add_middleware(RequestAuditMiddleware, database=database)
    app.add_middleware(TraceMiddleware)
    # Outer CORS preserves browser visibility of handled and unexpected API errors.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Trace-ID", "Idempotency-Replayed"],
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(catalog_router, prefix="/api/v1")
    app.include_router(circulation_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    return app


app = create_app()
