"""Health and readiness probe endpoints."""

import pyogrio
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Health & Monitoring"])


@router.get(
    "/health",
    summary="Liveness Probe",
    description="Returns 200 OK if service process is running and responding.",
    status_code=status.HTTP_200_OK,
)
async def health_check() -> dict[str, str]:
    """Liveness probe for orchestration and uptime checks."""
    return {"status": "healthy"}


@router.get(
    "/ready",
    summary="Readiness Probe",
    description="Validates that database connection is alive and necessary GDAL drivers are available.",
    status_code=status.HTTP_200_OK,
)
async def readiness_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Readiness probe evaluating database connection and GDAL OGR driver availability."""
    checks: dict[str, bool] = {"database": False, "gdal_drivers": False}
    details: dict[str, str] = {}

    # 1. Test database connection
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.error("Readiness check DB failure: %s", e)
        details["database_error"] = str(e)

    # 2. Test GDAL driver availability in pyogrio
    try:
        drivers = pyogrio.list_drivers()
        has_shp = "ESRI Shapefile" in drivers
        has_kml = "KML" in drivers or "LIBKML" in drivers
        checks["gdal_drivers"] = has_shp and has_kml
        if not checks["gdal_drivers"]:
            details["missing_drivers"] = f"ESRI Shapefile: {has_shp}, KML/LIBKML: {has_kml}"
    except Exception as e:
        logger.error("Readiness check GDAL driver failure: %s", e)
        details["gdal_error"] = str(e)

    all_ready = all(checks.values())
    http_status = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ready" if all_ready else "not_ready",
            "checks": checks,
            "details": details,
        },
    )
