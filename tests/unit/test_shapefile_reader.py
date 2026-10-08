"""Unit tests for Shapefile reader, attribute decoding, and CRS heuristics."""

from pathlib import Path

import numpy as np
import pyogrio.raw
import pyproj
import pytest
import shapely
from shapely.geometry import Polygon

from app.core.errors import CrsUndefinedException
from app.services.readers.shapefile_reader import ShapefileReader


def test_shapefile_reader_with_prj(tmp_path: Path) -> None:
    shp_file = tmp_path / "parcels.shp"
    poly = Polygon(
        [(580000.0, 2210000.0), (580100.0, 2210000.0), (580100.0, 2210100.0), (580000.0, 2210100.0)]
    )
    geometries = np.array([shapely.to_wkb(poly)], dtype=object)
    field_data = [np.array(["Plot A"], dtype=object), np.array([123], dtype=np.int32)]
    fields = ["name", "plot_num"]

    crs_wkt = pyproj.CRS.from_epsg(32643).to_wkt()
    pyogrio.raw.write(
        str(shp_file),
        geometry=geometries,
        field_data=field_data,
        fields=fields,
        geometry_type="Polygon",
        crs=crs_wkt,
    )

    reader = ShapefileReader()
    metadata, features = reader.read(shp_file)

    assert metadata.crs == "EPSG:32643"
    assert not metadata.crs_assumed
    assert metadata.feature_count == 1
    assert features[0].properties["name"] == "Plot A"
    assert features[0].properties["plot_num"] == 123


def test_shapefile_missing_prj_assumed_geographic(tmp_path: Path) -> None:
    shp_file = tmp_path / "noprj_geo.shp"
    # Coordinates inside lon [-180, 180], lat [-90, 90]
    poly = Polygon([(73.0, 19.0), (73.1, 19.0), (73.1, 19.1), (73.0, 19.1)])
    geometries = np.array([shapely.to_wkb(poly)], dtype=object)
    field_data = [np.array(["Unprojected"], dtype=object)]
    fields = ["name"]

    pyogrio.raw.write(
        str(shp_file),
        geometry=geometries,
        field_data=field_data,
        fields=fields,
        geometry_type="Polygon",
        crs=None,
    )
    # Ensure no .prj exists
    prj = tmp_path / "noprj_geo.prj"
    if prj.exists():
        prj.unlink()

    reader = ShapefileReader()
    metadata, features = reader.read(shp_file)

    assert metadata.crs == "EPSG:4326"
    assert metadata.crs_assumed
    assert len(metadata.warnings) > 0
    assert "EPSG:4326 (WGS 84) was assumed" in metadata.warnings[0]


def test_shapefile_missing_prj_exceeding_geographic_raises(tmp_path: Path) -> None:
    shp_file = tmp_path / "noprj_projected.shp"
    # Coordinates in large projected meters (x=580000, y=2210000)
    poly = Polygon(
        [(580000.0, 2210000.0), (580100.0, 2210000.0), (580100.0, 2210100.0), (580000.0, 2210100.0)]
    )
    geometries = np.array([shapely.to_wkb(poly)], dtype=object)
    field_data = [np.array(["Missing PRJ"], dtype=object)]
    fields = ["name"]

    pyogrio.raw.write(
        str(shp_file),
        geometry=geometries,
        field_data=field_data,
        fields=fields,
        geometry_type="Polygon",
        crs=None,
    )
    prj = tmp_path / "noprj_projected.prj"
    if prj.exists():
        prj.unlink()

    reader = ShapefileReader()
    with pytest.raises(CrsUndefinedException, match="outside geographic bounds"):
        reader.read(shp_file)


def test_sanitize_attribute_values() -> None:
    from datetime import date, datetime

    from app.services.readers.shapefile_reader import _sanitize_attribute_value

    assert _sanitize_attribute_value(None) is None
    assert _sanitize_attribute_value(float("nan")) is None
    assert _sanitize_attribute_value(float("inf")) is None
    assert _sanitize_attribute_value(np.float64(42.5)) == 42.5
    assert _sanitize_attribute_value(np.int64(100)) == 100
    assert _sanitize_attribute_value(date(2025, 1, 1)) == "2025-01-01"
    assert "2025-01-01" in _sanitize_attribute_value(datetime(2025, 1, 1, 12, 0))
    assert _sanitize_attribute_value(b"test string") == "test string"
    assert _sanitize_attribute_value([1, np.int32(2), None]) == [1, 2, None]
    assert _sanitize_attribute_value({"key": np.int32(5)}) == {"key": 5}
