"""SQLAlchemy 2.0 ORM models for UploadedFile and Feature entities."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class UploadedFile(Base):
    """Represents an uploaded geospatial archive or document."""

    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)  # SHAPEFILE | KML
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    feature_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    crs: Mapped[str] = mapped_column(String(64), nullable=False)
    crs_wkt: Mapped[str | None] = mapped_column(Text, nullable=True)
    crs_assumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warnings: Mapped[list[str]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), default=list
    )
    layer_names: Mapped[list[str]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), default=list
    )
    processing_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    features: Mapped[list["Feature"]] = relationship(
        "Feature",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Feature(Base):
    """Represents an individual geospatial feature and its calculated measurements."""

    __tablename__ = "features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_feature_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    layer_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    geometry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=True,
    )
    crs: Mapped[str] = mapped_column(String(64), nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        default=dict,
        nullable=False,
    )
    measurement_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # area | length | none
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    perimeter_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    geodesic_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    geodesic_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(128), nullable=True)
    measurement_status: Mapped[str] = mapped_column(String(32), nullable=False)
    measurement_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    file: Mapped["UploadedFile"] = relationship("UploadedFile", back_populates="features")

    __table_args__ = (
        Index("ix_features_file_id_feature_index", "file_id", "feature_index"),
        Index("ix_features_file_id_geometry_type", "file_id", "geometry_type"),
    )
