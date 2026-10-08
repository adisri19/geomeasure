"""Pydantic schemas for feature measurements, derived units, and summary statistics."""

from typing import Any

from pydantic import BaseModel, Field


class MeasurementDetail(BaseModel):
    """Detailed measurement results and auditable method metadata for a feature."""

    type: str = Field(
        ..., description="Measurement classification: area | length | none", examples=["area"]
    )
    status: str = Field(
        ...,
        description="Calculation status: OK | NOT_REQUIRED | SKIPPED_* | ERROR",
        examples=["OK"],
    )

    # Area Metrics (SI base: m2)
    area_m2: float | None = Field(
        None, description="Calculated area in square meters", examples=[12345.67]
    )
    area_hectares: float | None = Field(
        None, description="Derived area in hectares (ha)", examples=[1.2346]
    )
    area_acres: float | None = Field(
        None, description="Derived area in international acres", examples=[3.0506]
    )
    area_sq_km: float | None = Field(
        None, description="Derived area in square kilometers", examples=[0.0123]
    )
    perimeter_m: float | None = Field(
        None, description="Perimeter boundary in meters", examples=[456.7]
    )

    # Length Metrics (SI base: m)
    length_m: float | None = Field(
        None, description="Calculated line length in meters", examples=[1450.2]
    )
    length_km: float | None = Field(
        None, description="Derived length in kilometers", examples=[1.4502]
    )
    length_miles: float | None = Field(
        None, description="Derived length in statute miles", examples=[0.9011]
    )

    # Cross-validation & Audit Fields
    geodesic_area_m2: float | None = Field(
        None, description="Ellipsoidal geodesic area verification value (WGS84)"
    )
    geodesic_length_m: float | None = Field(
        None, description="Ellipsoidal geodesic length verification value (WGS84)"
    )
    method: str | None = Field(
        None, description="Projection strategy applied", examples=["UTM Zone 43N (EPSG:32643)"]
    )
    projected_crs: str | None = Field(
        None, description="Projected CRS code or proj4 string", examples=["EPSG:32643"]
    )
    note: str | None = Field(None, description="Informational or repair audit notes")


class FeatureItem(BaseModel):
    """Normalized feature record with geometry, properties, and measurements."""

    feature_index: int = Field(..., description="0-based sequence index within file", examples=[0])
    id: str | None = Field(
        None, description="Original source FID if available", examples=["FID_101"]
    )
    layer_name: str | None = Field(
        None, description="Originating layer or folder name", examples=["parcels"]
    )
    geometry_type: str = Field(..., description="OGC geometry type", examples=["Polygon"])
    crs: str = Field(..., description="Feature coordinate reference system", examples=["EPSG:4326"])
    geometry: dict[str, Any] | None = Field(
        None,
        description="GeoJSON geometry object in source CRS (optional based on include_geometry)",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Feature attributes and metadata"
    )
    measurement: MeasurementDetail


class SummaryArea(BaseModel):
    """Aggregated area metrics across all measured features."""

    square_meters: float = Field(..., examples=[1234567.89])
    hectares: float = Field(..., examples=[123.4568])
    square_kilometers: float = Field(..., examples=[1.2346])
    acres: float = Field(..., examples=[305.068])


class SummaryLength(BaseModel):
    """Aggregated length metrics across all measured features."""

    meters: float = Field(..., examples=[45678.9])
    kilometers: float = Field(..., examples=[45.6789])
    miles: float = Field(..., examples=[28.3835])


class MeasurementsSummary(BaseModel):
    """Cumulative summary totals across features in the file."""

    feature_count: int = Field(..., description="Total feature count in file", examples=[120])
    measured_count: int = Field(
        ..., description="Count of successfully measured features", examples=[110]
    )
    skipped_count: int = Field(
        ..., description="Count of non-measured or skipped features", examples=[10]
    )
    total_area: SummaryArea
    total_length: SummaryLength
    geometry_type_counts: dict[str, int] = Field(
        ...,
        description="Histogram of geometry types",
        examples=[{"Polygon": 80, "LineString": 30, "Point": 10}],
    )


class PaginationMeta(BaseModel):
    """Pagination metadata with navigational links."""

    limit: int = Field(..., examples=[100])
    offset: int = Field(..., examples=[0])
    total: int = Field(..., examples=[120])
    next: str | None = Field(
        None, examples=["/api/files/abc123/measurements/?limit=100&offset=100"]
    )
    previous: str | None = Field(None, examples=[None])


class MeasurementsResponse(BaseModel):
    """Complete measurement response schema matching evaluation contract."""

    file_id: str = Field(..., examples=["abc123"])
    crs: str = Field(..., examples=["EPSG:4326"])
    status: str = Field(..., examples=["COMPLETED"])
    summary: MeasurementsSummary
    pagination: PaginationMeta
    features: list[FeatureItem]
