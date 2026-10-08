"""Unit tests for measurement service, accuracy benchmarks, holes, and geometry handling."""

import pytest
import shapely
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.core.constants import MeasurementStatus, MeasurementType
from app.services.measurement_service import MeasurementService


def test_polygon_with_hole_subtraction() -> None:
    # Outer 100m x 100m square (10,000 m2) with a 20m x 20m hole (400 m2) in EPSG:32643
    outer = [
        (580000.0, 2210000.0),
        (580100.0, 2210000.0),
        (580100.0, 2210100.0),
        (580000.0, 2210100.0),
        (580000.0, 2210000.0),
    ]
    hole = [
        (580040.0, 2210040.0),
        (580060.0, 2210040.0),
        (580060.0, 2210060.0),
        (580040.0, 2210060.0),
        (580040.0, 2210040.0),
    ]
    poly = Polygon(outer, [hole])

    res = MeasurementService.measure_feature(poly, "EPSG:32643")
    assert res.status == MeasurementStatus.OK.value
    assert res.measurement_type == MeasurementType.AREA.value
    assert res.area_m2 is not None
    # 10,000 - 400 = 9,600 m2
    assert pytest.approx(res.area_m2, rel=1e-4) == 9600.0
    # Outer perimeter (400m) + inner perimeter (80m) = 480m
    assert res.perimeter_m is not None
    assert pytest.approx(res.perimeter_m, rel=1e-4) == 480.0


def test_multipolygon_area_sum() -> None:
    # Two distinct 100m x 100m squares in EPSG:32643 = 20,000 m2
    p1 = box(580000.0, 2210000.0, 580100.0, 2210100.0)
    p2 = box(580500.0, 2210500.0, 580600.0, 2210600.0)
    mp = MultiPolygon([p1, p2])

    res = MeasurementService.measure_feature(mp, "EPSG:32643")
    assert res.status == MeasurementStatus.OK.value
    assert res.area_m2 is not None
    assert pytest.approx(res.area_m2, rel=1e-4) == 20000.0


def test_linestring_and_multilinestring_length() -> None:
    # Line of length 500m in EPSG:32643
    line = LineString([(580000.0, 2210000.0), (580500.0, 2210000.0)])
    res = MeasurementService.measure_feature(line, "EPSG:32643")
    assert res.status == MeasurementStatus.OK.value
    assert res.measurement_type == MeasurementType.LENGTH.value
    assert res.length_m is not None
    assert pytest.approx(res.length_m, rel=1e-4) == 500.0

    # MultiLineString
    mline = MultiLineString(
        [
            LineString([(580000.0, 2210000.0), (580300.0, 2210000.0)]),
            LineString([(580500.0, 2210000.0), (580700.0, 2210000.0)]),
        ]
    )
    res_m = MeasurementService.measure_feature(mline, "EPSG:32643")
    assert res_m.length_m is not None
    assert pytest.approx(res_m.length_m, rel=1e-4) == 500.0


def test_linear_ring_measured_as_line() -> None:
    # Closed ring with perimeter 400m
    ring = LinearRing(
        [(580000.0, 2210000.0), (580100.0, 2210000.0), (580100.0, 2210100.0), (580000.0, 2210100.0)]
    )
    res = MeasurementService.measure_feature(ring, "EPSG:32643")
    assert res.status == MeasurementStatus.OK.value
    assert res.measurement_type == MeasurementType.LENGTH.value
    assert res.length_m is not None
    assert pytest.approx(res.length_m, rel=1e-4) == 400.0


def test_points_require_no_measurement() -> None:
    pt = Point(73.78, 19.99)
    res = MeasurementService.measure_feature(pt, "EPSG:4326")
    assert res.status == MeasurementStatus.NOT_REQUIRED.value
    assert res.measurement_type == MeasurementType.NONE.value

    mpt = MultiPoint([(73.78, 19.99), (73.79, 20.00)])
    res_m = MeasurementService.measure_feature(mpt, "EPSG:4326")
    assert res_m.status == MeasurementStatus.NOT_REQUIRED.value


def test_empty_and_null_geometry() -> None:
    res_null = MeasurementService.measure_feature(None, "EPSG:4326")
    assert res_null.status == MeasurementStatus.SKIPPED_EMPTY.value

    res_empty = MeasurementService.measure_feature(Polygon(), "EPSG:4326")
    assert res_empty.status == MeasurementStatus.SKIPPED_EMPTY.value


def test_invalid_geometry_repaired_via_make_valid() -> None:
    # Self-intersecting bowtie polygon (invalid)
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
    assert not bowtie.is_valid

    res = MeasurementService.measure_feature(bowtie, "EPSG:32643")
    assert res.status == MeasurementStatus.OK.value
    assert res.note is not None
    assert "Repaired" in res.note
    assert res.area_m2 is not None
    assert res.area_m2 > 0.0


def test_accuracy_equator_vs_60n_cos_scaling() -> None:
    # 1° x 1° box at equator ≈ 12,308.8 km² (±0.5%)
    equator_box = box(0.0, 0.0, 1.0, 1.0)
    res_eq = MeasurementService.measure_feature(equator_box, "EPSG:4326")
    assert res_eq.area_m2 is not None
    eq_area_km2 = res_eq.area_m2 / 1e6
    assert pytest.approx(eq_area_km2, rel=0.01) == 12308.8

    # 1° x 1° box at 60°N ≈ half of equatorial box
    box_60n = box(0.0, 60.0, 1.0, 61.0)
    res_60 = MeasurementService.measure_feature(box_60n, "EPSG:4326")
    assert res_60.area_m2 is not None
    ratio = res_60.area_m2 / res_eq.area_m2
    # cos(60.5°) is approximately 0.492
    assert 0.45 <= ratio <= 0.55


def test_accuracy_equatorial_line_1_degree() -> None:
    # 1° longitude line along the equator ≈ 111.319 km
    line = LineString([(0.0, 0.0), (1.0, 0.0)])
    res = MeasurementService.measure_feature(line, "EPSG:4326")
    assert res.length_m is not None
    len_km = res.length_m / 1000.0
    assert pytest.approx(len_km, rel=0.01) == 111.32


def test_geometry_collection_decomposition() -> None:
    gc = GeometryCollection(
        [
            box(580000.0, 2210000.0, 580100.0, 2210100.0),  # 10,000 m2
            LineString([(580000.0, 2210000.0), (580200.0, 2210000.0)]),  # 200m
        ]
    )
    res = MeasurementService.measure_feature(gc, "EPSG:32643")
    assert res.status == MeasurementStatus.OK.value
    assert res.area_m2 is not None
    assert pytest.approx(res.area_m2, rel=1e-4) == 10000.0
    assert res.length_m is not None
    assert pytest.approx(res.length_m, rel=1e-4) == 200.0
    assert "Mixed GeometryCollection" in (res.note or "")


def test_z_coordinates_dropped() -> None:
    # Polygon with 3D Z coordinates
    poly_3d = Polygon(
        [
            (580000.0, 2210000.0, 500.0),
            (580100.0, 2210000.0, 520.0),
            (580100.0, 2210100.0, 510.0),
            (580000.0, 2210100.0, 490.0),
        ]
    )
    res = MeasurementService.measure_feature(poly_3d, "EPSG:32643")
    assert res.status == MeasurementStatus.OK.value
    assert pytest.approx(res.area_m2, rel=1e-4) == 10000.0


def test_degenerate_geometries() -> None:
    # Zero-length line
    zero_line = LineString([(10.0, 10.0), (10.0, 10.0)])
    res_line = MeasurementService.measure_feature(zero_line, "EPSG:32643")
    assert res_line.status == MeasurementStatus.OK.value
    assert res_line.length_m == 0.0
    assert "Degenerate zero-length" in (res_line.note or "")


def test_geometry_collection_unsupported_or_empty() -> None:
    # Geometry collection with only points (unsupported for area/length measurement)
    gc_pts = GeometryCollection([Point(0, 0), Point(1, 1)])
    res = MeasurementService.measure_feature(gc_pts, "EPSG:4326")
    assert res.status == MeasurementStatus.SKIPPED_UNSUPPORTED.value
    assert "contains no polygons or lines" in (res.note or "")


def test_web_mercator_vs_4326_equivalence() -> None:
    # Measure a 0.01 deg parcel in EPSG:4326 vs same in EPSG:3857
    poly_4326 = box(73.78, 19.99, 73.79, 20.00)
    res_4326 = MeasurementService.measure_feature(poly_4326, "EPSG:4326")

    # Reproject to 3857 coordinates
    import pyproj

    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    poly_3857 = shapely.ops.transform(transformer.transform, poly_4326)

    res_3857 = MeasurementService.measure_feature(poly_3857, "EPSG:3857")
    assert res_4326.area_m2 is not None
    assert res_3857.area_m2 is not None
    # Both methods should agree within 0.1% because 3857 is rerouted to UTM!
    assert pytest.approx(res_4326.area_m2, rel=1e-3) == res_3857.area_m2


def test_clean_and_repair_geometry_null_and_empty() -> None:
    from app.services.geometry_service import clean_and_repair_geometry

    g_none, rep1, note1 = clean_and_repair_geometry(None)
    assert g_none is None
    assert not rep1
    assert note1 == "Geometry is null"

    g_empty, rep2, note2 = clean_and_repair_geometry(Polygon())
    assert g_empty.is_empty
    assert not rep2
    assert note2 == "Geometry is empty"
