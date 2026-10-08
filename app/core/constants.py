"""Domain constants, enums, unit conversion factors, and error codes."""

from enum import StrEnum


class FileStatus(StrEnum):
    """Lifecycle status of an uploaded geospatial file."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileType(StrEnum):
    """Supported file archive/format types."""

    SHAPEFILE = "SHAPEFILE"
    KML = "KML"


class GeometryType(StrEnum):
    """Normalized OGC/GeoJSON geometry types."""

    POINT = "Point"
    LINESTRING = "LineString"
    POLYGON = "Polygon"
    MULTI_POINT = "MultiPoint"
    MULTI_LINESTRING = "MultiLineString"
    MULTI_POLYGON = "MultiPolygon"
    GEOMETRY_COLLECTION = "GeometryCollection"
    NONE = "None"
    UNKNOWN = "Unknown"


class MeasurementType(StrEnum):
    """Type of measurement calculated for a feature."""

    AREA = "area"
    LENGTH = "length"
    NONE = "none"


class MeasurementStatus(StrEnum):
    """Status outcome of a measurement calculation."""

    OK = "OK"
    NOT_REQUIRED = "NOT_REQUIRED"
    SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
    SKIPPED_EMPTY = "SKIPPED_EMPTY"
    SKIPPED_INVALID = "SKIPPED_INVALID"
    ERROR = "ERROR"


class ErrorCode(StrEnum):
    """Standardized error codes returned in API error envelopes."""

    FILE_REQUIRED = "FILE_REQUIRED"
    EMPTY_FILE = "EMPTY_FILE"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    CONTENT_TYPE_MISMATCH = "CONTENT_TYPE_MISMATCH"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_ARCHIVE = "INVALID_ARCHIVE"
    UNSAFE_ARCHIVE = "UNSAFE_ARCHIVE"
    SHAPEFILE_NOT_FOUND = "SHAPEFILE_NOT_FOUND"
    SHAPEFILE_MISSING_COMPONENTS = "SHAPEFILE_MISSING_COMPONENTS"
    INVALID_KML = "INVALID_KML"
    NO_FEATURES = "NO_FEATURES"
    CRS_UNDEFINED = "CRS_UNDEFINED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_NOT_READY = "FILE_NOT_READY"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# --- Unit Conversion Constants (Exact & Standardized) ---
# SI base units: meters (m), square meters (m²)

# Area Conversions from m²
SQ_METERS_TO_HECTARES: float = 1e-4
SQ_METERS_TO_SQ_KILOMETERS: float = 1e-6
SQ_METERS_TO_ACRES: float = 0.00024710538146717

# Length Conversions from m
METERS_TO_KILOMETERS: float = 1e-3
METERS_TO_MILES: float = 0.000621371192237334

# Linear Foot conversions to Meters
INTERNATIONAL_FOOT_TO_METERS: float = 0.3048
US_SURVEY_FOOT_TO_METERS: float = 1200.0 / 3937.0  # ≈ 0.3048006096012192

# Default tolerance for geodesic vs projected validation (0.5%)
DEFAULT_GEODESIC_TOLERANCE_PCT: float = 0.5
