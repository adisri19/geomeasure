"""Unit tests for KML reader, XML security defenses (XXE), and geometry extraction."""

from pathlib import Path

import pytest
from shapely.geometry import Polygon

from app.core.errors import InvalidKmlException, NoFeaturesException
from app.services.readers.kml_reader import KmlReader


def test_kml_reader_parses_polygon_with_hole(tmp_path: Path) -> None:
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Parcels</name>
      <Placemark id="p1">
        <name>Plot With Pond</name>
        <ExtendedData>
          <Data name="owner"><value>Farmer Ramesh</value></Data>
        </ExtendedData>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                73.00,19.00,100
                73.02,19.00,100
                73.02,19.02,100
                73.00,19.02,100
                73.00,19.00,100
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
          <innerBoundaryIs>
            <LinearRing>
              <coordinates>
                73.005,19.005,50
                73.015,19.005,50
                73.015,19.015,50
                73.005,19.015,50
                73.005,19.005,50
              </coordinates>
            </LinearRing>
          </innerBoundaryIs>
        </Polygon>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "holes.kml"
    kml_file.write_text(kml_content)

    reader = KmlReader()
    metadata, features = reader.read(kml_file)

    assert metadata.crs == "EPSG:4326"
    assert metadata.feature_count == 1
    assert "Parcels" in metadata.layer_names

    f = features[0]
    assert f.source_feature_id == "p1"
    assert f.layer_name == "Parcels"
    assert f.properties.get("owner") == "Farmer Ramesh"
    assert f.properties.get("name") == "Plot With Pond"
    assert f.geometry_type == "Polygon"
    assert isinstance(f.geometry, Polygon)
    # Check that hole was parsed
    assert len(f.geometry.interiors) == 1
    # Check that altitude was dropped (2D)
    assert not f.geometry.has_z


def test_kml_reader_blocks_xxe_payload(tmp_path: Path) -> None:
    xxe_payload = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE kml [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>&xxe;</name>
  </Document>
</kml>
"""
    xxe_file = tmp_path / "xxe_exploit.kml"
    xxe_file.write_text(xxe_payload)

    reader = KmlReader()
    with pytest.raises(InvalidKmlException, match="insecure XML entities"):
        reader.read(xxe_file)


def test_kml_reader_malformed_xml(tmp_path: Path) -> None:
    bad_xml = tmp_path / "bad.kml"
    bad_xml.write_text("<kml><Document><unclosed_tag>broken</Document></kml>")

    reader = KmlReader()
    with pytest.raises(InvalidKmlException, match="Malformed or invalid XML"):
        reader.read(bad_xml)


def test_kml_reader_no_features(tmp_path: Path) -> None:
    empty_kml = tmp_path / "empty_doc.kml"
    empty_kml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document><name>No Placemarks</name></Document>
</kml>
""")

    reader = KmlReader()
    with pytest.raises(NoFeaturesException, match="No Placemarks or geospatial features found"):
        reader.read(empty_kml)


def test_kml_reader_multigeometry_and_linearring(tmp_path: Path) -> None:
    kml_text = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark id="mg1">
      <name>Multi Lines</name>
      <MultiGeometry>
        <LineString>
          <coordinates>73.0,19.0 73.1,19.0</coordinates>
        </LineString>
        <LineString>
          <coordinates>73.1,19.1 73.2,19.1</coordinates>
        </LineString>
      </MultiGeometry>
    </Placemark>
    <Placemark id="lr1">
      <name>Closed LinearRing</name>
      <LinearRing>
        <coordinates>73.0,19.0 73.1,19.0 73.1,19.1 73.0,19.0</coordinates>
      </LinearRing>
    </Placemark>
    <Placemark id="empty_pm">
      <name>Empty Placemark</name>
    </Placemark>
    <NetworkLink>
      <name>Ignored Remote Link</name>
    </NetworkLink>
  </Document>
</kml>
"""
    kml_file = tmp_path / "multi.kml"
    kml_file.write_text(kml_text)

    reader = KmlReader()
    metadata, features = reader.read(kml_file)

    assert metadata.feature_count == 3
    assert features[0].geometry_type == "MultiLineString"
    assert features[1].geometry_type == "LineString"
    assert features[2].geometry is None
    assert features[2].geometry_type == "None"
