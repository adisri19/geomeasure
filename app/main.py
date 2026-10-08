"""Main FastAPI application factory, lifespan setup, middleware, and router mounts."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.router import api_router
from app.api.routes.health import router as root_health_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, request_id_ctx, setup_logging
from app.db.session import init_db

settings = get_settings()
logger = get_logger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware establishing and propagating correlation X-Request-ID across the request lifecycle."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Extract existing header or generate a fresh ID
        req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:10]}"
        token = request_id_ctx.set(req_id)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"
            return response
        finally:
            request_id_ctx.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown hooks."""
    # 1. Initialize logging
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting Geospatial File Measurement API (env=%s)", settings.ENVIRONMENT)

    # 2. Ensure database schema is initialized
    init_db()
    logger.info("Database schema validated and ready")

    yield

    logger.info("Shutting down Geospatial File Measurement API")


def create_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Geospatial File Measurement API",
        description=(
            "Production-grade backend service accepting Shapefile (.zip) and KML (.kml) geospatial files, "
            "normalizing geometry features, projecting geographic coordinates to metric projected CRSs, "
            "and calculating high-precision area and length measurements with geodesic cross-validation."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Register error handlers
    register_exception_handlers(app)

    # Register middleware
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    app.include_router(api_router, prefix="/api")
    app.include_router(root_health_router)

    return app


app = create_application()
