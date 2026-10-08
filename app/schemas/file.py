"""Pydantic schemas for file upload responses and metadata representations."""

from datetime import datetime

from pydantic import BaseModel, Field


class FileLinks(BaseModel):
    """HATEOAS navigational links."""

    self: str = Field(..., description="URL to retrieve file metadata")
    measurements: str = Field(..., description="URL to retrieve feature measurements")


class FileInfo(BaseModel):
    """File information schema.

    Contains all mandatory fields verbatim from the evaluation specification:
    - id
    - filename
    - feature_count
    - crs
    - status
    Plus supplemental operational metadata.
    """

    # MANDATORY EVALUATION FIELDS (exact names)
    id: str = Field(..., description="Unique file identifier", examples=["abc123"])
    filename: str = Field(..., description="Sanitized original filename", examples=["survey.kml"])
    feature_count: int = Field(
        ..., description="Total count of features in the file", examples=[120]
    )
    crs: str = Field(
        ..., description="Coordinate Reference System identifier", examples=["EPSG:4326"]
    )
    status: str = Field(..., description="Processing lifecycle state", examples=["COMPLETED"])

    # SUPPLEMENTAL METADATA FIELDS
    file_type: str | None = Field(None, description="SHAPEFILE or KML", examples=["KML"])
    size_bytes: int | None = Field(None, description="Size of file in bytes", examples=[1048576])
    sha256: str | None = Field(None, description="SHA256 digest of original uploaded bytes")
    geometry_type_counts: dict[str, int] | None = Field(
        None,
        description="Feature counts grouped by geometry type",
        examples=[{"Polygon": 80, "LineString": 30, "Point": 10}],
    )
    crs_assumed: bool = Field(
        False, description="Whether CRS was assumed via coordinate bounds heuristic"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings recorded during processing"
    )
    error: str | None = Field(None, description="Error message if processing FAILED")
    created_at: datetime | None = Field(None, description="Upload timestamp")
    processed_at: datetime | None = Field(None, description="Processing completion timestamp")
    processing_ms: float | None = Field(
        None, description="Elapsed processing duration in milliseconds"
    )
    links: FileLinks | None = Field(None, description="Related endpoint hyperlinks")


class FileListResponse(BaseModel):
    """Paginated collection of uploaded files."""

    items: list[FileInfo]
    total: int = Field(..., description="Total number of uploaded files matching criteria")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")
