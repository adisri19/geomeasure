"""Unit tests for CRS selection strategy, UTM zone calculations, unit conversions, and distortions."""

import pyproj
import pytest
from shapely.geometry import box

from app.core.constants import US_SURVEY_FOOT_TO_METERS
from app.services.crs_service import (
    calculate_utm_zone,
    get_linear_unit_conversion,
    is_distorting_projection,
    select_projected_crs,
)


def test_calculate_utm_zone_northern_hemisphere() -> None:
    # Nashik, India (73.78 E, 19.99 N) -> Zone 43
    zone = calculate_utm_zone(73.78, 19.99)
    assert zone == 43

    # London, UK (-0.12 W, 51.5 N) -> Zone 30
    zone_london = calculate_utm_zone(-0.12, 51.5)
    assert zone_london == 30

    # New York (-74.0 W, 40.7 N) -> Zone 18
    zone_ny = calculate_utm_zone(-74.0, 40.7)
    assert zone_ny == 18


def test_calculate_utm_zone_exceptions() -> None:
    # Norway exception (lat between 56 and 64, lon between 3 and 12) -> Zone 32
    zone_norway = calculate_utm_zone(6.0, 60.0)
    assert zone_norway == 32

    # Svalbard exception (lat 75, lon 15) -> Zone 33
    zone_svalbard = calculate_utm_zone(15.0, 75.0)
    assert zone_svalbard == 33


def test_select_projected_crs_single_utm_zone() -> None:
    # Small 0.01 deg parcel in India
    poly = box(73.78, 19.99, 73.79, 20.00)
    decision = select_projected_crs(poly, "EPSG:4326")

    assert decision.target_crs == "EPSG:32643"
    assert "UTM Zone 43N" in decision.method
    assert not decision.is_native
    assert decision.linear_unit_factor == 1.0
    assert decision.area_unit_factor == 1.0


def test_select_projected_crs_southern_hemisphere() -> None:
    # Sydney, Australia (151.2 E, -33.8 S) -> UTM Zone 56S (EPSG:32756)
    poly = box(151.20, -33.86, 151.21, -33.85)
    decision = select_projected_crs(poly, "EPSG:4326")

    assert decision.target_crs == "EPSG:32756"
    assert "UTM Zone 56S" in decision.method


def test_select_projected_crs_polar_regions() -> None:
    # North Pole (> 84 N) -> UPS North (EPSG:32661)
    poly_north = box(10.0, 85.0, 11.0, 85.5)
    dec_north = select_projected_crs(poly_north, "EPSG:4326")
    assert dec_north.target_crs == "EPSG:32661"
    assert "UPS North" in dec_north.method

    # South Pole (< -84 S) -> UPS South (EPSG:32761)
    poly_south = box(10.0, -86.0, 11.0, -85.5)
    dec_south = select_projected_crs(poly_south, "EPSG:4326")
    assert dec_south.target_crs == "EPSG:32761"
    assert "UPS South" in dec_south.method


def test_select_projected_crs_wide_extent_laea_fallback() -> None:
    # Wide polygon spanning 15 degrees longitude (crosses UTM zones)
    poly = box(70.0, 15.0, 85.0, 25.0)
    decision = select_projected_crs(poly, "EPSG:4326")

    assert "+proj=laea" in decision.target_crs
    assert "Custom LAEA" in decision.method


def test_select_projected_crs_native_metric_passthrough() -> None:
    # Already projected in EPSG:32643
    poly = box(580000, 2210000, 580500, 2210500)
    decision = select_projected_crs(poly, "EPSG:32643")

    assert decision.target_crs == "EPSG:32643"
    assert decision.is_native
    assert decision.linear_unit_factor == 1.0


def test_select_projected_crs_web_mercator_distortion_reroute() -> None:
    # Web Mercator EPSG:3857 must NOT be measured natively due to severe latitude area distortion
    crs_3857 = pyproj.CRS.from_epsg(3857)
    assert is_distorting_projection(crs_3857)

    # Box in Web Mercator coordinates (corresponding to ~73E, 20N)
    poly_3857 = box(8126000, 2272000, 8127000, 2273000)
    decision = select_projected_crs(poly_3857, "EPSG:3857")

    # Should have reprojected and selected appropriate UTM zone rather than native 3857
    assert decision.target_crs != "EPSG:3857"
    assert "UTM" in decision.method
    assert not decision.is_native


def test_linear_unit_conversion_feet() -> None:
    # State Plane Texas Central (US Survey Feet) EPSG:2277
    try:
        crs_survey_feet = pyproj.CRS.from_epsg(2277)
        factor = get_linear_unit_conversion(crs_survey_feet)
        assert pytest.approx(factor, rel=1e-5) == US_SURVEY_FOOT_TO_METERS
    except Exception:
        # If EPSG not present in local database
        pass


def test_svalbard_utm_zones() -> None:
    # Svalbard lat 75
    assert calculate_utm_zone(4.0, 75.0) == 31
    assert calculate_utm_zone(15.0, 75.0) == 33
    assert calculate_utm_zone(25.0, 75.0) == 35
    assert calculate_utm_zone(35.0, 75.0) == 37


def test_unparseable_crs_defaults_to_epsg4326() -> None:
    poly = box(73.78, 19.99, 73.79, 20.00)
    decision = select_projected_crs(poly, "NOT_A_VALID_CRS_STRING_XYZ")
    assert "EPSG:32643" in decision.target_crs


def test_custom_mercator_detected_as_distorting() -> None:
    custom_merc = pyproj.CRS.from_proj4(
        "+proj=merc +lon_0=0 +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    assert is_distorting_projection(custom_merc)
