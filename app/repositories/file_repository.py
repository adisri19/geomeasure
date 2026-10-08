"""SQLAlchemy repository for UploadedFile and Feature records."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FileStatus, MeasurementStatus
from app.db.models import Feature, UploadedFile


class FileRepository:
    """Repository handling all CRUD and aggregate operations for uploaded files and features."""

    @staticmethod
    def create_file(session: Session, file_record: UploadedFile) -> UploadedFile:
        """Persist a new UploadedFile entity."""
        session.add(file_record)
        session.commit()
        session.refresh(file_record)
        return file_record

    @staticmethod
    def get_file(session: Session, file_id: str) -> UploadedFile | None:
        """Fetch an UploadedFile by primary key id."""
        stmt = select(UploadedFile).where(UploadedFile.id == file_id)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def list_files(
        session: Session,
        limit: int = 100,
        offset: int = 0,
        status_filter: str | None = None,
    ) -> tuple[list[UploadedFile], int]:
        """Fetch paginated list of uploaded files, optionally filtered by status."""
        query = select(UploadedFile)
        count_query = select(func.count()).select_from(UploadedFile)

        if status_filter:
            query = query.where(UploadedFile.status == status_filter)
            count_query = count_query.where(UploadedFile.status == status_filter)

        total = session.execute(count_query).scalar_one()
        records = (
            session.execute(
                query.order_by(UploadedFile.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return list(records), total

    @staticmethod
    def delete_file(session: Session, file_id: str) -> bool:
        """Delete an uploaded file and all its associated features via cascade."""
        file_rec = session.get(UploadedFile, file_id)
        if not file_rec:
            return False
        session.delete(file_rec)
        session.commit()
        return True

    @staticmethod
    def mark_processing(session: Session, file_id: str) -> None:
        """Update file status to PROCESSING."""
        file_rec = session.get(UploadedFile, file_id)
        if file_rec:
            file_rec.status = FileStatus.PROCESSING.value
            session.commit()

    @staticmethod
    def mark_completed(
        session: Session,
        file_id: str,
        feature_count: int,
        crs: str,
        crs_wkt: str | None,
        crs_assumed: bool,
        layer_names: list[str],
        warnings: list[str],
        processing_ms: float,
    ) -> None:
        """Update file status to COMPLETED with final summary metadata."""
        file_rec = session.get(UploadedFile, file_id)
        if file_rec:
            file_rec.status = FileStatus.COMPLETED.value
            file_rec.feature_count = feature_count
            file_rec.crs = crs
            file_rec.crs_wkt = crs_wkt
            file_rec.crs_assumed = crs_assumed
            file_rec.layer_names = layer_names
            file_rec.warnings = warnings
            file_rec.processing_ms = processing_ms
            file_rec.processed_at = datetime.now(UTC)
            session.commit()

    @staticmethod
    def mark_failed(
        session: Session,
        file_id: str,
        error_code: str,
        error_message: str,
        processing_ms: float | None = None,
    ) -> None:
        """Update file status to FAILED with error code and description."""
        file_rec = session.get(UploadedFile, file_id)
        if file_rec:
            file_rec.status = FileStatus.FAILED.value
            file_rec.error_code = error_code
            file_rec.error_message = error_message
            file_rec.processing_ms = processing_ms
            file_rec.processed_at = datetime.now(UTC)
            session.commit()

    @staticmethod
    def bulk_insert_features(
        session: Session,
        features: list[Feature],
        batch_size: int = 500,
    ) -> None:
        """Insert features in batches for efficient bulk database writes."""
        for i in range(0, len(features), batch_size):
            batch = features[i : i + batch_size]
            session.add_all(batch)
            session.flush()
        session.commit()

    @staticmethod
    def get_features(
        session: Session,
        file_id: str,
        limit: int = 100,
        offset: int = 0,
        geometry_type: str | None = None,
    ) -> tuple[list[Feature], int]:
        """Fetch paginated features for a given file with optional geometry_type filter."""
        query = select(Feature).where(Feature.file_id == file_id)
        count_query = select(func.count()).select_from(Feature).where(Feature.file_id == file_id)

        if geometry_type:
            query = query.where(Feature.geometry_type == geometry_type)
            count_query = count_query.where(Feature.geometry_type == geometry_type)

        total = session.execute(count_query).scalar_one()
        items = (
            session.execute(query.order_by(Feature.feature_index.asc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )
        return list(items), total

    @staticmethod
    def get_feature_by_index(
        session: Session,
        file_id: str,
        feature_index: int,
    ) -> Feature | None:
        """Fetch a single feature by its 0-based index."""
        stmt = (
            select(Feature)
            .where(Feature.file_id == file_id)
            .where(Feature.feature_index == feature_index)
        )
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_file_summary(session: Session, file_id: str) -> dict[str, Any]:
        """Calculate aggregate counts and metric totals across features of a file."""
        # 1. Total feature count
        count_stmt = select(func.count()).select_from(Feature).where(Feature.file_id == file_id)
        total_count = session.execute(count_stmt).scalar_one() or 0

        # 2. Measured count vs skipped count
        measured_stmt = (
            select(func.count())
            .select_from(Feature)
            .where(Feature.file_id == file_id)
            .where(Feature.measurement_status == MeasurementStatus.OK.value)
        )
        measured_count = session.execute(measured_stmt).scalar_one() or 0
        skipped_count = total_count - measured_count

        # 3. Geometry type breakdown
        geom_types_stmt = (
            select(Feature.geometry_type, func.count(Feature.id))
            .where(Feature.file_id == file_id)
            .group_by(Feature.geometry_type)
        )
        geom_counts: dict[str, int] = {}
        for g_type, count in session.execute(geom_types_stmt):
            geom_counts[str(g_type)] = int(count)

        # 4. Total area sum in m2
        area_sum_stmt = (
            select(func.coalesce(func.sum(Feature.area_m2), 0.0))
            .where(Feature.file_id == file_id)
            .where(Feature.measurement_status == MeasurementStatus.OK.value)
        )
        total_area_m2 = float(session.execute(area_sum_stmt).scalar_one() or 0.0)

        # 5. Total length sum in m
        length_sum_stmt = (
            select(func.coalesce(func.sum(Feature.length_m), 0.0))
            .where(Feature.file_id == file_id)
            .where(Feature.measurement_status == MeasurementStatus.OK.value)
        )
        total_length_m = float(session.execute(length_sum_stmt).scalar_one() or 0.0)

        return {
            "feature_count": total_count,
            "measured_count": measured_count,
            "skipped_count": skipped_count,
            "geometry_type_counts": geom_counts,
            "total_area_m2": total_area_m2,
            "total_length_m": total_length_m,
        }
