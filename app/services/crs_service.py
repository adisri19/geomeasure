"""Cartographic Reference System (CRS) selection, reprojection caching, and validation service."""

import math
from dataclasses import dataclass
from functools import lru_cache

import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform

from app.core.constants import (
    INTERNATIONAL_FOOT_TO_METERS,
    US_SURVEY_FOOT_TO_METERS,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Known severely distorting conformal Mercator projections (area inflates dramatically away from equator)
MERCATOR_DISTORTING_EPSG = {"EPSG:3857", "EPSG:900913", "EPSG:3785", "EPSG:102100", "EPSG:102113"}


@dataclass(frozen=True)
class ProjectedCrsDecision:
    """Strategy decision regarding the projected coordinate system to use for measurement."""

    target_crs: str
    method: str
    is_native: bool
    linear_unit_factor: float
    area_unit_factor: float


@lru_cache(maxsize=256)
def get_transformer(src_crs_str: str, dst_crs_str: str) -> Transformer:
    """Retrieve or create a cached pyproj Transformer with always_xy=True."""
    return Transformer.from_crs(src_crs_str, dst_crs_str, always_xy=True)


def is_distorting_projection(crs: CRS) -> bool:
    """Check if the given projected CRS suffers from major conformal area distortion (e.g. Web Mercator)."""
    # Check EPSG code
    epsg = crs.to_epsg()
    if epsg and f"EPSG:{epsg}" in MERCATOR_DISTORTING_EPSG:
        return True

    # Check proj name or parameters
    name = (crs.name or "").lower()
    proj_type = crs.to_dict().get("proj", "").lower() if hasattr(crs, "to_dict") else ""

    if "mercator" in name and "transverse" not in name and "universal" not in name:
        return True
    return proj_type == "merc"


def get_linear_unit_conversion(crs: CRS) -> float:
    """Determine the conversion factor from native CRS linear units to SI meters."""
    try:
        if crs.axis_info and len(crs.axis_info) > 0:
            unit_name = (crs.axis_info[0].unit_name or "").lower()
            factor = crs.axis_info[0].unit_conversion_factor
            if factor is not None and factor > 0:
                return float(factor)

            if "us survey foot" in unit_name or "survey_ft" in unit_name:
                return US_SURVEY_FOOT_TO_METERS
            if "foot" in unit_name or "feet" in unit_name or "ft" in unit_name:
                return INTERNATIONAL_FOOT_TO_METERS
    except Exception as e:
        logger.debug("Could not inspect CRS axis_info: %s", e)

    return 1.0


def calculate_utm_zone(lon: float, lat: float) -> int:
    """Calculate the standard UTM zone number for a given longitude and latitude.

    Handles standard 6-degree zones as well as Norway and Svalbard exceptions.
    """
    # Clamp longitude to [-180, 180)
    lon_normalized = (lon + 180.0) % 360.0 - 180.0

    # Norway exception: lat 56 to 64, lon 3 to 12
    if 56.0 <= lat < 64.0 and 3.0 <= lon_normalized < 12.0:
        return 32

    # Svalbard exceptions: lat 72 to 84
    if 72.0 <= lat < 84.0:
        if 0.0 <= lon_normalized < 9.0:
            return 31
        if 9.0 <= lon_normalized < 21.0:
            return 33
        if 21.0 <= lon_normalized < 33.0:
            return 35
        if 33.0 <= lon_normalized < 42.0:
            return 37

    zone = int((lon_normalized + 180.0) // 6.0) + 1
    return max(1, min(60, zone))


def select_projected_crs(
    geometry: shapely.Geometry,
    source_crs_str: str,
) -> ProjectedCrsDecision:
    """Determine the optimal projected CRS for measurement based on geometry bounds and source CRS.

    Decision Algorithm:
    1. If source CRS is already projected:
       - If Web Mercator or distorting: reproject via geographic coordinates to UTM or LAEA.
       - Otherwise: keep native projection and normalize linear/area units (e.g. feet -> meters).
    2. If source CRS is geographic (e.g. EPSG:4326):
       - If polar (|lat| >= 84°): use UPS North (EPSG:32661) or South (EPSG:32761).
       - If longitudinal extent <= 6°: use local UTM zone based on centroid.
       - If longitudinal extent > 6°: use custom Lambert Azimuthal Equal-Area (LAEA) centered on centroid.
    """
    try:
        src_crs = CRS.from_user_input(source_crs_str)
    except Exception:
        # Default fallback to WGS84 geographic if input cannot be parsed
        src_crs = CRS.from_user_input("EPSG:4326")

    # CASE 1: Source CRS is already projected
    if src_crs.is_projected:
        if not is_distorting_projection(src_crs):
            # Safe native projected CRS
            factor = get_linear_unit_conversion(src_crs)
            method_desc = f"Native Projected ({src_crs.name or source_crs_str})"
            return ProjectedCrsDecision(
                target_crs=source_crs_str,
                method=method_desc,
                is_native=True,
                linear_unit_factor=factor,
                area_unit_factor=factor * factor,
            )

        # Distorting projection (e.g. Web Mercator) -> Reproject to geographic first
        logger.info(
            "Source CRS %s is distorting. Reprojecting to geographic for projected selection.",
            source_crs_str,
        )
        t_to_geo = get_transformer(source_crs_str, "EPSG:4326")
        geo_geom = transform(t_to_geo.transform, geometry)
    else:
        geo_geom = geometry

    # CASE 2: Geographic coordinates (or reprojected from distorting projection)
    bounds = geo_geom.bounds  # (minx, miny, maxx, maxy) in lon, lat
    min_lon, min_lat, max_lon, max_lat = bounds[0], bounds[1], bounds[2], bounds[3]

    # Calculate centroid / representative point
    centroid = geo_geom.centroid
    lon_c = (
        float(centroid.x)
        if not (centroid.is_empty or math.isnan(centroid.x))
        else (min_lon + max_lon) / 2.0
    )
    lat_c = (
        float(centroid.y)
        if not (centroid.is_empty or math.isnan(centroid.y))
        else (min_lat + max_lat) / 2.0
    )

    # Ensure lon_c is in [-180, 180]
    lon_c = (lon_c + 180.0) % 360.0 - 180.0
    lat_c = max(-90.0, min(90.0, lat_c))

    # Polar region check (|lat| >= 84.0°)
    if abs(lat_c) >= 84.0:
        if lat_c >= 0:
            return ProjectedCrsDecision(
                target_crs="EPSG:32661",
                method="UPS North (EPSG:32661)",
                is_native=False,
                linear_unit_factor=1.0,
                area_unit_factor=1.0,
            )
        return ProjectedCrsDecision(
            target_crs="EPSG:32761",
            method="UPS South (EPSG:32761)",
            is_native=False,
            linear_unit_factor=1.0,
            area_unit_factor=1.0,
        )

    # Longitudinal span
    lon_span = abs(max_lon - min_lon)

    # If within a single UTM zone (<= 6 degrees)
    if lon_span <= 6.0:
        utm_zone = calculate_utm_zone(lon_c, lat_c)
        if lat_c >= 0:
            epsg_code = 32600 + utm_zone
            method = f"UTM Zone {utm_zone}N (EPSG:{epsg_code})"
        else:
            epsg_code = 32700 + utm_zone
            method = f"UTM Zone {utm_zone}S (EPSG:{epsg_code})"

        target_crs_str = f"EPSG:{epsg_code}"
        return ProjectedCrsDecision(
            target_crs=target_crs_str,
            method=method,
            is_native=False,
            linear_unit_factor=1.0,
            area_unit_factor=1.0,
        )

    # Spans multiple UTM zones or antimeridian -> Custom Lambert Azimuthal Equal-Area (LAEA)
    laea_proj_string = (
        f"+proj=laea +lat_0={lat_c:.6f} +lon_0={lon_c:.6f} +datum=WGS84 +units=m +no_defs"
    )
    method = f"Custom LAEA (lat_0={lat_c:.2f}, lon_0={lon_c:.2f})"
    return ProjectedCrsDecision(
        target_crs=laea_proj_string,
        method=method,
        is_native=False,
        linear_unit_factor=1.0,
        area_unit_factor=1.0,
    )


def reproject_geometry(
    geometry: shapely.Geometry,
    source_crs_str: str,
    target_crs_str: str,
) -> shapely.Geometry:
    """Reproject a Shapely geometry from source to target CRS using cached Transformer."""
    if source_crs_str == target_crs_str:
        return geometry

    transformer = get_transformer(source_crs_str, target_crs_str)
    return transform(transformer.transform, geometry)
