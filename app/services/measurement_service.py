"""Measurement service executing projected calculations and geodesic cross-validation."""

from dataclasses import dataclass

import shapely
from pyproj import CRS, Geod
from shapely.ops import transform

from app.core.config import get_settings
from app.core.constants import (
    DEFAULT_GEODESIC_TOLERANCE_PCT,
    MeasurementStatus,
    MeasurementType,
)
from app.core.logging import get_logger
from app.services.crs_service import (
    ProjectedCrsDecision,
    get_transformer,
    reproject_geometry,
    select_projected_crs,
)
from app.services.geometry_service import clean_and_repair_geometry

logger = get_logger(__name__)
settings = get_settings()

# WGS84 Geodesic model for ellipsoid calculations
WGS84_GEOD = Geod(ellps="WGS84")


@dataclass
class CalculatedMeasurement:
    """Calculated measurement result for an individual feature."""

    measurement_type: str
    status: str
    area_m2: float | None = None
    length_m: float | None = None
    perimeter_m: float | None = None
    geodesic_area_m2: float | None = None
    geodesic_length_m: float | None = None
    method: str | None = None
    projected_crs: str | None = None
    note: str | None = None


class MeasurementService:
    """Service orchestrating geometry projection, metric calculation, and geodesic auditing."""

    @classmethod
    def measure_feature(
        cls,
        geom: shapely.Geometry | None,
        source_crs_str: str,
    ) -> CalculatedMeasurement:
        """Measure an individual feature with failure isolation.

        Catches any per-feature geometric or projection exceptions and returns an ERROR status
        rather than aborting processing of the entire file.
        """
        try:
            return cls._execute_measurement(geom, source_crs_str)
        except Exception as e:
            logger.warning("Feature measurement failed: %s", e)
            return CalculatedMeasurement(
                measurement_type=MeasurementType.NONE.value,
                status=MeasurementStatus.ERROR.value,
                note=f"Measurement error: {e}",
            )

    @classmethod
    def _execute_measurement(
        cls,
        raw_geom: shapely.Geometry | None,
        source_crs_str: str,
    ) -> CalculatedMeasurement:
        """Execute calculation logic for a single geometry."""
        # 1. Check for empty or null geometry
        if raw_geom is None or raw_geom.is_empty:
            return CalculatedMeasurement(
                measurement_type=MeasurementType.NONE.value,
                status=MeasurementStatus.SKIPPED_EMPTY.value,
                note="Geometry is empty or null",
            )

        # 2. Point / MultiPoint Handling: zero dimensions
        if raw_geom.geom_type in ("Point", "MultiPoint"):
            return CalculatedMeasurement(
                measurement_type=MeasurementType.NONE.value,
                status=MeasurementStatus.NOT_REQUIRED.value,
                note="Point geometry has zero dimension; measurement not required",
            )

        # 3. Clean and repair geometry (force 2D, make_valid)
        clean_geom, was_repaired, repair_note = clean_and_repair_geometry(raw_geom)
        if clean_geom is None or clean_geom.is_empty:
            return CalculatedMeasurement(
                measurement_type=MeasurementType.NONE.value,
                status=MeasurementStatus.SKIPPED_INVALID.value,
                note=repair_note or "Geometry is topologically invalid and could not be repaired",
            )

        notes: list[str] = []
        if was_repaired and repair_note:
            notes.append(repair_note)

        # 4. Projected CRS Selection
        decision: ProjectedCrsDecision = select_projected_crs(clean_geom, source_crs_str)

        # Guard: Never measure in unprojected geographic degrees
        dest_crs = CRS.from_user_input(decision.target_crs)
        if not dest_crs.is_projected:
            raise ValueError(
                f"Selected CRS '{decision.target_crs}' is geographic. Area/length cannot be computed in degrees."
            )

        # 5. Reproject geometry to target projected CRS
        if decision.is_native:
            proj_geom = clean_geom
        else:
            proj_geom = reproject_geometry(clean_geom, source_crs_str, decision.target_crs)

        # 6. Execute measurement by geometry type
        g_type = proj_geom.geom_type

        # Handle degenerate collapsed geometries (e.g. LineString with identical points -> Point)
        if raw_geom.geom_type in ("LineString", "MultiLineString") and clean_geom.geom_type in (
            "Point",
            "MultiPoint",
        ):
            return CalculatedMeasurement(
                measurement_type=MeasurementType.LENGTH.value,
                status=MeasurementStatus.OK.value,
                length_m=0.0,
                geodesic_length_m=0.0,
                method=decision.method,
                projected_crs=decision.target_crs,
                note="Degenerate zero-length line (collapsed to point)",
            )

        if raw_geom.geom_type in ("Polygon", "MultiPolygon") and clean_geom.geom_type in (
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
        ):
            return CalculatedMeasurement(
                measurement_type=MeasurementType.AREA.value,
                status=MeasurementStatus.OK.value,
                area_m2=0.0,
                perimeter_m=0.0,
                method=decision.method,
                projected_crs=decision.target_crs,
                note="Degenerate zero-area polygon (collapsed)",
            )

        # Case A: Polygons
        if g_type in ("Polygon", "MultiPolygon"):
            raw_area = float(proj_geom.area)
            raw_perimeter = float(proj_geom.length)

            area_m2 = raw_area * decision.area_unit_factor
            perimeter_m = raw_perimeter * decision.linear_unit_factor

            # Geodesic verification on WGS84
            geod_area_m2 = cls._compute_geodesic_area(clean_geom, source_crs_str)
            if geod_area_m2 is not None and geod_area_m2 > 0:
                diff_pct = abs(area_m2 - geod_area_m2) / geod_area_m2 * 100.0
                tolerance = getattr(
                    settings, "GEODESIC_TOLERANCE_PCT", DEFAULT_GEODESIC_TOLERANCE_PCT
                )
                if diff_pct > tolerance:
                    notes.append(
                        f"Projected area differs from ellipsoidal geodesic by {diff_pct:.2f}% (tolerance {tolerance}%)"
                    )

            if area_m2 == 0.0:
                notes.append("Degenerate polygon with zero area")

            return CalculatedMeasurement(
                measurement_type=MeasurementType.AREA.value,
                status=MeasurementStatus.OK.value,
                area_m2=area_m2,
                perimeter_m=perimeter_m,
                geodesic_area_m2=geod_area_m2,
                method=decision.method,
                projected_crs=decision.target_crs,
                note="; ".join(notes) if notes else None,
            )

        # Case B: LineStrings
        if g_type in ("LineString", "MultiLineString", "LinearRing"):
            raw_length = float(proj_geom.length)
            length_m = raw_length * decision.linear_unit_factor

            # Geodesic verification on WGS84
            geod_len_m = cls._compute_geodesic_length(clean_geom, source_crs_str)
            if geod_len_m is not None and geod_len_m > 0:
                diff_pct = abs(length_m - geod_len_m) / geod_len_m * 100.0
                tolerance = getattr(
                    settings, "GEODESIC_TOLERANCE_PCT", DEFAULT_GEODESIC_TOLERANCE_PCT
                )
                if diff_pct > tolerance:
                    notes.append(
                        f"Projected length differs from ellipsoidal geodesic by {diff_pct:.2f}% (tolerance {tolerance}%)"
                    )

            if length_m == 0.0:
                notes.append("Degenerate line with zero length")

            return CalculatedMeasurement(
                measurement_type=MeasurementType.LENGTH.value,
                status=MeasurementStatus.OK.value,
                length_m=length_m,
                geodesic_length_m=geod_len_m,
                method=decision.method,
                projected_crs=decision.target_crs,
                note="; ".join(notes) if notes else None,
            )

        # Case C: GeometryCollection
        if g_type == "GeometryCollection":
            return cls._measure_geometry_collection(clean_geom, decision, source_crs_str, notes)

        # Case D: Unsupported geometry type
        return CalculatedMeasurement(
            measurement_type=MeasurementType.NONE.value,
            status=MeasurementStatus.SKIPPED_UNSUPPORTED.value,
            note=f"Unsupported geometry type '{g_type}' for measurement",
        )

    @classmethod
    def _measure_geometry_collection(
        cls,
        geom_col: shapely.Geometry,
        decision: ProjectedCrsDecision,
        source_crs_str: str,
        prior_notes: list[str],
    ) -> CalculatedMeasurement:
        """Decompose GeometryCollection into polygons and lines, measuring supported sub-elements."""
        polys = [g for g in geom_col.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        lines = [
            g
            for g in geom_col.geoms
            if g.geom_type in ("LineString", "MultiLineString", "LinearRing")
        ]

        if not polys and not lines:
            return CalculatedMeasurement(
                measurement_type=MeasurementType.NONE.value,
                status=MeasurementStatus.SKIPPED_UNSUPPORTED.value,
                note="GeometryCollection contains no polygons or lines",
            )

        notes = list(prior_notes)
        total_area = 0.0
        total_len = 0.0

        for p in polys:
            p_proj = (
                p
                if decision.is_native
                else reproject_geometry(p, source_crs_str, decision.target_crs)
            )
            total_area += float(p_proj.area) * decision.area_unit_factor

        for line in lines:
            l_proj = (
                line
                if decision.is_native
                else reproject_geometry(line, source_crs_str, decision.target_crs)
            )
            total_len += float(l_proj.length) * decision.linear_unit_factor

        if polys and not lines:
            m_type = MeasurementType.AREA.value
            notes.append(f"GeometryCollection decomposed into {len(polys)} polygon(s)")
            return CalculatedMeasurement(
                measurement_type=m_type,
                status=MeasurementStatus.OK.value,
                area_m2=total_area,
                method=decision.method,
                projected_crs=decision.target_crs,
                note="; ".join(notes),
            )

        if lines and not polys:
            m_type = MeasurementType.LENGTH.value
            notes.append(f"GeometryCollection decomposed into {len(lines)} line(s)")
            return CalculatedMeasurement(
                measurement_type=m_type,
                status=MeasurementStatus.OK.value,
                length_m=total_len,
                method=decision.method,
                projected_crs=decision.target_crs,
                note="; ".join(notes),
            )

        # Mixed collection: provide area and record line length in notes
        notes.append(
            f"Mixed GeometryCollection: {len(polys)} polygon(s) (area={total_area:.2f} m²), {len(lines)} line(s) (length={total_len:.2f} m)"
        )
        return CalculatedMeasurement(
            measurement_type=MeasurementType.AREA.value,
            status=MeasurementStatus.OK.value,
            area_m2=total_area,
            length_m=total_len,
            method=decision.method,
            projected_crs=decision.target_crs,
            note="; ".join(notes),
        )

    @classmethod
    def _compute_geodesic_area(cls, geom: shapely.Geometry, source_crs_str: str) -> float | None:
        """Compute geodesic area on the WGS84 ellipsoid for cross-validation."""
        try:
            # Reproject to WGS84 if source is not EPSG:4326
            if source_crs_str.upper() != "EPSG:4326":
                t = get_transformer(source_crs_str, "EPSG:4326")
                wgs84_geom = transform(t.transform, geom)
            else:
                wgs84_geom = geom

            area, _ = WGS84_GEOD.geometry_area_perimeter(wgs84_geom)
            return abs(float(area))
        except Exception as e:
            logger.debug("Geodesic area computation skipped: %s", e)
            return None

    @classmethod
    def _compute_geodesic_length(cls, geom: shapely.Geometry, source_crs_str: str) -> float | None:
        """Compute geodesic length on the WGS84 ellipsoid for cross-validation."""
        try:
            if source_crs_str.upper() != "EPSG:4326":
                t = get_transformer(source_crs_str, "EPSG:4326")
                wgs84_geom = transform(t.transform, geom)
            else:
                wgs84_geom = geom

            length = WGS84_GEOD.geometry_length(wgs84_geom)
            return float(length)
        except Exception as e:
            logger.debug("Geodesic length computation skipped: %s", e)
            return None
