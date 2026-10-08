"""File upload, metadata inspection, and geospatial measurement endpoints."""

from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi import (
    Path as PathParam,
)
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.constants import (
    METERS_TO_KILOMETERS,
    METERS_TO_MILES,
    SQ_METERS_TO_ACRES,
    SQ_METERS_TO_HECTARES,
    SQ_METERS_TO_SQ_KILOMETERS,
    FileStatus,
)
from app.core.errors import (
    FileNotFoundException,
    FileNotReadyException,
    FileRequiredException,
    ProcessingFailedException,
)
from app.core.logging import get_logger
from app.db.models import Feature, UploadedFile
from app.repositories.file_repository import FileRepository
from app.schemas.errors import ErrorResponse
from app.schemas.feature import (
    FeatureItem,
    MeasurementDetail,
    MeasurementsResponse,
    MeasurementsSummary,
    PaginationMeta,
    SummaryArea,
    SummaryLength,
)
from app.schemas.file import FileInfo, FileLinks, FileListResponse
from app.services.upload_service import handle_file_upload

logger = get_logger(__name__)
router = APIRouter(prefix="/files", tags=["Files & Measurements"])


def _build_file_links(file_id: str) -> FileLinks:
    """Construct self and measurements links for an uploaded file."""
    return FileLinks(
        self=f"/api/files/{file_id}/",
        measurements=f"/api/files/{file_id}/measurements/",
    )


def _file_to_schema(file_rec: UploadedFile, summary: dict[str, Any] | None = None) -> FileInfo:
    """Map SQLAlchemy UploadedFile model to FileInfo response schema."""
    geom_counts = summary.get("geometry_type_counts") if summary else None
    return FileInfo(
        id=file_rec.id,
        filename=file_rec.filename,
        feature_count=file_rec.feature_count,
        crs=file_rec.crs,
        status=file_rec.status,
        file_type=file_rec.file_type,
        size_bytes=file_rec.size_bytes,
        sha256=file_rec.sha256,
        geometry_type_counts=geom_counts,
        crs_assumed=file_rec.crs_assumed,
        warnings=file_rec.warnings or [],
        error=file_rec.error_message if file_rec.status == FileStatus.FAILED.value else None,
        created_at=file_rec.created_at,
        processed_at=file_rec.processed_at,
        processing_ms=file_rec.processing_ms,
        links=_build_file_links(file_rec.id),
    )


def _feature_to_schema(
    f: Feature,
    include_geom: bool = True,
    precision: int = 4,
) -> FeatureItem:
    """Map Feature model to FeatureItem with formatted units and rounding."""
    # Convert area metrics
    area_m2 = round(f.area_m2, precision) if f.area_m2 is not None else None
    area_ha = round(f.area_m2 * SQ_METERS_TO_HECTARES, precision) if f.area_m2 is not None else None
    area_ac = round(f.area_m2 * SQ_METERS_TO_ACRES, precision) if f.area_m2 is not None else None
    area_km2 = (
        round(f.area_m2 * SQ_METERS_TO_SQ_KILOMETERS, precision) if f.area_m2 is not None else None
    )
    perim_m = round(f.perimeter_m, precision) if f.perimeter_m is not None else None

    # Convert length metrics
    len_m = round(f.length_m, precision) if f.length_m is not None else None
    len_km = round(f.length_m * METERS_TO_KILOMETERS, precision) if f.length_m is not None else None
    len_mi = round(f.length_m * METERS_TO_MILES, precision) if f.length_m is not None else None

    # Cross-validation geodesic metrics
    geod_area = round(f.geodesic_area_m2, precision) if f.geodesic_area_m2 is not None else None
    geod_len = round(f.geodesic_length_m, precision) if f.geodesic_length_m is not None else None

    meas_detail = MeasurementDetail(
        type=f.measurement_type,
        status=f.measurement_status,
        area_m2=area_m2,
        area_hectares=area_ha,
        area_acres=area_ac,
        area_sq_km=area_km2,
        perimeter_m=perim_m,
        length_m=len_m,
        length_km=len_km,
        length_miles=len_mi,
        geodesic_area_m2=geod_area,
        geodesic_length_m=geod_len,
        method=f.measurement_method,
        projected_crs=f.measurement_crs,
        note=f.measurement_note,
    )

    return FeatureItem(
        feature_index=f.feature_index,
        id=f.source_feature_id,
        layer_name=f.layer_name,
        geometry_type=f.geometry_type,
        crs=f.crs,
        geometry=f.geometry if include_geom else None,
        properties=f.properties or {},
        measurement=meas_detail,
    )


# --- 1. POST /api/files/ ---
@router.post(
    "/",
    summary="Upload and Process Geospatial File",
    description="Upload a Shapefile archive (.zip) or KML document (.kml) for validation, projection, and measurement.",
    status_code=status.HTTP_201_CREATED,
    response_model=FileInfo,
    responses={
        201: {"description": "File uploaded and processed synchronously"},
        202: {
            "description": "File uploaded and scheduled for asynchronous background processing (?async=true)"
        },
        400: {"model": ErrorResponse, "description": "Empty file uploaded"},
        413: {"model": ErrorResponse, "description": "Upload size exceeds permitted limit"},
        415: {"model": ErrorResponse, "description": "Unsupported media type or format mismatch"},
        422: {
            "model": ErrorResponse,
            "description": "Invalid archive, missing shapefile components, malformed XML, or undefined CRS",
        },
    },
)
async def upload_file(
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Geospatial file (.zip Shapefile or .kml)"),
    async_mode: bool = Query(False, alias="async", description="Execute processing asynchronously"),
    db: Session = Depends(get_db),
) -> FileInfo:
    """Accept multipart upload, validate format, and process features."""
    if not file or not file.filename:
        raise FileRequiredException("Upload file is missing or has an empty filename")

    file_rec = await handle_file_upload(
        upload_file=file,
        session=db,
        is_async=async_mode,
        background_tasks=background_tasks if async_mode else None,
    )

    location_url = f"/api/files/{file_rec.id}/"
    response.headers["Location"] = location_url

    if async_mode:
        response.status_code = status.HTTP_202_ACCEPTED

    summary = (
        FileRepository.get_file_summary(db, file_rec.id)
        if file_rec.status == FileStatus.COMPLETED.value
        else None
    )
    return _file_to_schema(file_rec, summary)


# Alias without trailing slash
router.add_api_route(
    "",
    upload_file,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)


# --- 2. GET /api/files/ (List) ---
@router.get(
    "/",
    summary="List Uploaded Files",
    description="Retrieve a paginated list of uploaded files with optional status filtering.",
    response_model=FileListResponse,
)
def list_files(
    limit: int = Query(100, ge=1, le=1000, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    file_status: str | None = Query(
        None, alias="status", description="Filter by status (COMPLETED, PENDING, FAILED)"
    ),
    db: Session = Depends(get_db),
) -> FileListResponse:
    files, total = FileRepository.list_files(
        db, limit=limit, offset=offset, status_filter=file_status
    )
    items = [_file_to_schema(f) for f in files]
    return FileListResponse(items=items, total=total, limit=limit, offset=offset)


router.add_api_route(
    "",
    list_files,
    methods=["GET"],
    include_in_schema=False,
)


# --- 3. GET /api/files/{id}/ ---
@router.get(
    "/{file_id}/",
    summary="Get File Information",
    description="Retrieve file processing status, metadata, counts, and CRS information.",
    response_model=FileInfo,
    responses={
        200: {"description": "File metadata retrieved successfully"},
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
def get_file_info(
    file_id: str = PathParam(..., description="Unique file ID"),
    db: Session = Depends(get_db),
) -> FileInfo:
    file_rec = FileRepository.get_file(db, file_id)
    if not file_rec:
        raise FileNotFoundException(file_id=file_id)

    summary = (
        FileRepository.get_file_summary(db, file_id)
        if file_rec.status == FileStatus.COMPLETED.value
        else None
    )
    return _file_to_schema(file_rec, summary)


router.add_api_route(
    "/{file_id}",
    get_file_info,
    methods=["GET"],
    include_in_schema=False,
)


# --- 4. GET /api/files/{id}/measurements/ ---
@router.get(
    "/{file_id}/measurements/",
    summary="Get Feature Measurements",
    description="Retrieve calculated area and length measurements, derived units, summary statistics, and features.",
    response_model=MeasurementsResponse,
    responses={
        200: {"description": "Measurements and summary retrieved successfully"},
        404: {"model": ErrorResponse, "description": "File not found"},
        409: {"model": ErrorResponse, "description": "File is still PENDING or PROCESSING"},
        422: {"model": ErrorResponse, "description": "File processing FAILED"},
    },
)
def get_measurements(
    file_id: str = PathParam(..., description="Unique file ID"),
    limit: int = Query(100, ge=1, le=1000, description="Features per page"),
    offset: int = Query(0, ge=0, description="Features offset"),
    geometry_type: str | None = Query(
        None, description="Filter features by geometry type (e.g. Polygon, LineString)"
    ),
    include_geometry: bool = Query(
        True, description="Whether to include full GeoJSON geometry objects"
    ),
    precision: int = Query(
        4, ge=0, le=10, description="Decimal precision for displayed numeric units"
    ),
    db: Session = Depends(get_db),
) -> MeasurementsResponse:
    file_rec = FileRepository.get_file(db, file_id)
    if not file_rec:
        raise FileNotFoundException(file_id=file_id)

    if file_rec.status in (FileStatus.PENDING.value, FileStatus.PROCESSING.value):
        raise FileNotReadyException(file_id=file_id, current_status=file_rec.status)

    if file_rec.status == FileStatus.FAILED.value:
        raise ProcessingFailedException(file_id=file_id, reason=file_rec.error_message)

    # 1. Fetch paginated features
    features, total = FileRepository.get_features(
        session=db,
        file_id=file_id,
        limit=limit,
        offset=offset,
        geometry_type=geometry_type,
    )

    # 2. Fetch summary aggregates
    summary_data = FileRepository.get_file_summary(db, file_id)

    total_area_m2 = summary_data["total_area_m2"]
    total_len_m = summary_data["total_length_m"]

    summary_area = SummaryArea(
        square_meters=round(total_area_m2, precision),
        hectares=round(total_area_m2 * SQ_METERS_TO_HECTARES, precision),
        square_kilometers=round(total_area_m2 * SQ_METERS_TO_SQ_KILOMETERS, precision),
        acres=round(total_area_m2 * SQ_METERS_TO_ACRES, precision),
    )

    summary_length = SummaryLength(
        meters=round(total_len_m, precision),
        kilometers=round(total_len_m * METERS_TO_KILOMETERS, precision),
        miles=round(total_len_m * METERS_TO_MILES, precision),
    )

    summary = MeasurementsSummary(
        feature_count=summary_data["feature_count"],
        measured_count=summary_data["measured_count"],
        skipped_count=summary_data["skipped_count"],
        total_area=summary_area,
        total_length=summary_length,
        geometry_type_counts=summary_data["geometry_type_counts"],
    )

    # 3. Build pagination links
    base_url = f"/api/files/{file_id}/measurements/?limit={limit}"
    if geometry_type:
        base_url += f"&geometry_type={geometry_type}"

    next_url = f"{base_url}&offset={offset + limit}" if (offset + limit) < total else None
    prev_url = f"{base_url}&offset={max(0, offset - limit)}" if offset > 0 else None

    pagination = PaginationMeta(
        limit=limit,
        offset=offset,
        total=total,
        next=next_url,
        previous=prev_url,
    )

    # 4. Map feature items
    feature_items = [
        _feature_to_schema(f, include_geom=include_geometry, precision=precision) for f in features
    ]

    return MeasurementsResponse(
        file_id=file_id,
        crs=file_rec.crs,
        status=file_rec.status,
        summary=summary,
        pagination=pagination,
        features=feature_items,
    )


router.add_api_route(
    "/{file_id}/measurements",
    get_measurements,
    methods=["GET"],
    include_in_schema=False,
)


# --- 5. GET /api/files/{id}/features/{feature_index}/ ---
@router.get(
    "/{file_id}/features/{feature_index}/",
    summary="Get Single Feature Measurement",
    description="Retrieve measurement details for an individual feature by index.",
    response_model=FeatureItem,
    responses={
        200: {"description": "Feature retrieved successfully"},
        404: {"model": ErrorResponse, "description": "File or feature not found"},
    },
)
def get_single_feature(
    file_id: str = PathParam(..., description="Unique file ID"),
    feature_index: int = PathParam(..., ge=0, description="0-based feature index"),
    precision: int = Query(4, ge=0, le=10),
    db: Session = Depends(get_db),
) -> FeatureItem:
    file_rec = FileRepository.get_file(db, file_id)
    if not file_rec:
        raise FileNotFoundException(file_id=file_id)

    feature = FileRepository.get_feature_by_index(db, file_id, feature_index)
    if not feature:
        raise FileNotFoundException(
            file_id=file_id,
            message=f"Feature with index {feature_index} not found in file '{file_id}'",
        )

    return _feature_to_schema(feature, include_geom=True, precision=precision)


router.add_api_route(
    "/{file_id}/features/{feature_index}",
    get_single_feature,
    methods=["GET"],
    include_in_schema=False,
)


# --- 6. DELETE /api/files/{id}/ ---
@router.delete(
    "/{file_id}/",
    summary="Delete File and Measurements",
    description="Delete an uploaded file record and all its associated features.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "File and features deleted successfully"},
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
def delete_file(
    file_id: str = PathParam(..., description="Unique file ID"),
    db: Session = Depends(get_db),
) -> Response:
    deleted = FileRepository.delete_file(db, file_id)
    if not deleted:
        raise FileNotFoundException(file_id=file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


router.add_api_route(
    "/{file_id}",
    delete_file,
    methods=["DELETE"],
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
