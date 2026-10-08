"""Upload processing service orchestrating validation, reader extraction, and persistence."""

import tempfile
import time
from pathlib import Path
from typing import Any

import shapely.geometry
from fastapi import BackgroundTasks, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import ErrorCode, FileStatus, FileType
from app.core.errors import AppException, InternalException
from app.core.logging import get_logger
from app.db.models import Feature, UploadedFile
from app.db.session import SessionLocal
from app.repositories.file_repository import FileRepository
from app.services.file_validation import stream_validate_and_save
from app.services.measurement_service import CalculatedMeasurement, MeasurementService
from app.services.readers.factory import ReaderFactory
from app.services.zip_handler import SafeZipExtractor
from app.utils.ids import generate_file_id, sanitize_filename

logger = get_logger(__name__)
settings = get_settings()


def _execute_processing_pipeline(
    file_id: str,
    temp_file_path: Path,
    file_type: FileType,
    session: Session | None = None,
) -> None:
    """Worker function executing reading, projection, measurement, and persistence."""
    start_time = time.perf_counter()
    own_session = False
    if session is None:
        session = SessionLocal()
        own_session = True

    try:
        FileRepository.mark_processing(session, file_id)

        # 1. Select reader and extract features
        reader = ReaderFactory.get_reader(file_type)

        if file_type == FileType.SHAPEFILE:
            # Safely unpack zip archive into temporary directory
            with tempfile.TemporaryDirectory() as extract_dir_str:
                extract_path = Path(extract_dir_str)
                SafeZipExtractor.extract_and_find_shapefiles(temp_file_path, extract_path)
                file_metadata, raw_features = reader.read(extract_path)
        else:
            # Direct KML file read
            file_metadata, raw_features = reader.read(temp_file_path)

        # 2. Process features and measurements
        feature_models: list[Feature] = []

        for raw in raw_features:
            # Measure with per-feature error isolation
            measurement: CalculatedMeasurement = MeasurementService.measure_feature(
                geom=raw.geometry,
                source_crs_str=raw.crs,
            )

            # Convert Shapely geometry to GeoJSON dict in source CRS
            geojson_geom: dict[str, Any] | None = None
            if raw.geometry is not None and not raw.geometry.is_empty:
                try:
                    geojson_geom = shapely.geometry.mapping(raw.geometry)
                except Exception as e:
                    logger.warning("Failed to serialize geometry to GeoJSON: %s", e)
                    geojson_geom = None

            feat_record = Feature(
                file_id=file_id,
                feature_index=raw.feature_index,
                source_feature_id=raw.source_feature_id,
                layer_name=raw.layer_name,
                geometry_type=raw.geometry_type,
                geometry=geojson_geom,
                crs=raw.crs,
                properties=raw.properties,
                measurement_type=measurement.measurement_type,
                area_m2=measurement.area_m2,
                length_m=measurement.length_m,
                perimeter_m=measurement.perimeter_m,
                geodesic_area_m2=measurement.geodesic_area_m2,
                geodesic_length_m=measurement.geodesic_length_m,
                measurement_method=measurement.method,
                measurement_crs=measurement.projected_crs,
                measurement_status=measurement.status,
                measurement_note=measurement.note,
            )
            feature_models.append(feat_record)

        # 3. Bulk insert features
        FileRepository.bulk_insert_features(session, feature_models)

        # 4. Mark file completed
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        FileRepository.mark_completed(
            session=session,
            file_id=file_id,
            feature_count=len(feature_models),
            crs=file_metadata.crs,
            crs_wkt=file_metadata.crs_wkt,
            crs_assumed=file_metadata.crs_assumed,
            layer_names=file_metadata.layer_names,
            warnings=file_metadata.warnings,
            processing_ms=round(elapsed_ms, 2),
        )
        logger.info(
            "Successfully processed file %s with %d features in %.2f ms",
            file_id,
            len(feature_models),
            elapsed_ms,
        )

    except AppException as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.warning("Pipeline app exception for file %s: [%s] %s", file_id, e.code, e.message)
        FileRepository.mark_failed(
            session=session,
            file_id=file_id,
            error_code=e.code,
            error_message=e.message,
            processing_ms=round(elapsed_ms, 2),
        )
        raise
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.exception("Unexpected error processing file %s: %s", file_id, e)
        FileRepository.mark_failed(
            session=session,
            file_id=file_id,
            error_code=ErrorCode.INTERNAL_ERROR.value,
            error_message=f"Internal processing failure: {e}",
            processing_ms=round(elapsed_ms, 2),
        )
        raise InternalException(f"Processing failed: {e}") from e
    finally:
        if own_session and session is not None:
            session.close()
        # Clean up temporary upload file
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except Exception as e:
                logger.warning("Could not remove temp upload file %s: %s", temp_file_path, e)


async def handle_file_upload(
    upload_file: UploadFile,
    session: Session,
    is_async: bool = False,
    background_tasks: BackgroundTasks | None = None,
) -> UploadedFile:
    """Handle multipart file upload, validate, persist pending record, and trigger processing."""
    file_id = generate_file_id()
    clean_name = sanitize_filename(upload_file.filename)
    temp_path = settings.UPLOAD_DIR / f"{file_id}_{clean_name}"

    # 1. Stream, validate, sniff, and save to disk
    size_bytes, sha256_hex, file_type = await stream_validate_and_save(
        upload_file=upload_file,
        dest_path=temp_path,
    )

    # 2. Create initial database record with status PENDING
    file_record = UploadedFile(
        id=file_id,
        filename=clean_name,
        file_type=file_type.value,
        size_bytes=size_bytes,
        sha256=sha256_hex,
        feature_count=0,
        crs="PENDING",
        crs_assumed=False,
        status=FileStatus.PENDING.value,
        warnings=[],
        layer_names=[],
    )
    FileRepository.create_file(session, file_record)

    # 3. Dispatch to worker
    if is_async and background_tasks is not None:
        background_tasks.add_task(
            _execute_processing_pipeline,
            file_id=file_id,
            temp_file_path=temp_path,
            file_type=file_type,
            session=None,
        )
        return file_record

    # Synchronous processing on threadpool
    await run_in_threadpool(
        _execute_processing_pipeline,
        file_id=file_id,
        temp_file_path=temp_path,
        file_type=file_type,
        session=session,
    )

    # Refresh record from database to obtain final state
    updated_record = FileRepository.get_file(session, file_id)
    return updated_record or file_record
