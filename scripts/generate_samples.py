"""Generate sample geospatial files (KML and Shapefile ZIPs) for reviewer inspection and testing."""

import io
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pyogrio.raw
import pyproj
import shapely
from shapely.geometry import (
    LineString,
    Point,
    Polygon,
)

SAMPLE_DIR = Path("samples")
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def _zip_directory(source_dir: Path, zip_dest: Path, prefix: str = "") -> None:
    """Pack files from source directory into a zip archive with optional folder prefix."""
    with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                full_path = Path(root) / file
                arc_name = full_path.relative_to(source_dir)
                if prefix:
                    arc_name = Path(prefix) / arc_name
                zf.write(full_path, arc_name.as_posix())


# 1. Generate plots_4326.kml
def generate_plots_kml() -> None:
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Maharashtra Agricultural Survey</name>
    <Folder>
      <name>Parcels</name>
      <Placemark id="plot_nashik_01">
        <name>Nashik Vineyard Estate</name>
        <description>Prime vineyard parcel near Nashik, Maharashtra</description>
        <ExtendedData>
          <Data name="crop"><value>Grapes</value></Data>
          <Data name="soil_type"><value>Black Cotton</value></Data>
          <Data name="irrigation"><value>Drip</value></Data>
        </ExtendedData>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                73.7800,19.9900,0
                73.8000,19.9900,0
                73.8000,20.0100,0
                73.7800,20.0100,0
                73.7800,19.9900,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
          <innerBoundaryIs>
            <LinearRing>
              <coordinates>
                73.7850,19.9950,0
                73.7950,19.9950,0
                73.7950,20.0050,0
                73.7850,20.0050,0
                73.7850,19.9950,0
              </coordinates>
            </LinearRing>
          </innerBoundaryIs>
        </Polygon>
      </Placemark>
      <Placemark id="plot_london_02">
        <name>Greenwich Park (Zone 30N Test)</name>
        <description>Polygon in London demonstrating international UTM Zone 30N</description>
        <ExtendedData>
          <Data name="zone"><value>UTM 30N</value></Data>
        </ExtendedData>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                -0.0100,51.4700,0
                0.0100,51.4700,0
                0.0100,51.4900,0
                -0.0100,51.4900,0
                -0.0100,51.4700,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
      <Placemark id="empty_plot_03">
        <name>Unsurveyed Plot (Empty Geometry)</name>
        <description>Demonstrates graceful handling of empty geometry</description>
      </Placemark>
    </Folder>
    <Folder>
      <name>Infrastructure</name>
      <Placemark id="canal_01">
        <name>Godavari Irrigation Canal</name>
        <description>Main distribution canal line</description>
        <ExtendedData>
          <Data name="capacity_cusecs"><value>450</value></Data>
        </ExtendedData>
        <LineString>
          <coordinates>
            73.7500,19.9800,0
            73.7700,19.9850,0
            73.7900,20.0000,0
            73.8200,20.0150,0
          </coordinates>
        </LineString>
      </Placemark>
      <Placemark id="substation_01">
        <name>Nashik Grid Substation</name>
        <description>Electrical substation point</description>
        <Point>
          <coordinates>73.7850,19.9920,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    dest = SAMPLE_DIR / "plots_4326.kml"
    dest.write_text(kml_content)
    print(f"Generated {dest}")


# 2. Generate parcels_utm43n.zip (Projected CRS EPSG:32643)
def generate_parcels_utm43n() -> None:
    with tempfile.TemporaryDirectory() as td:
        shp_path = Path(td) / "parcels_utm43n.shp"

        # Coordinates in meters within UTM Zone 43N
        poly1 = Polygon(
            [
                (580000.0, 2210000.0),
                (580500.0, 2210000.0),
                (580500.0, 2210500.0),
                (580000.0, 2210500.0),
                (580000.0, 2210000.0),
            ]
        )  # 500m x 500m = 250,000 m2 (25 ha)

        poly2 = Polygon(
            [
                (581000.0, 2211000.0),
                (581200.0, 2211000.0),
                (581200.0, 2211200.0),
                (581000.0, 2211200.0),
                (581000.0, 2211000.0),
            ]
        )  # 200m x 200m = 40,000 m2 (4 ha)

        geometries = np.array([shapely.to_wkb(poly1), shapely.to_wkb(poly2)], dtype=object)
        field_data = [
            np.array(["Parcel A", "Parcel B"], dtype=object),
            np.array([25.0, 4.0], dtype=np.float64),
        ]
        fields = ["name", "nominal_ha"]

        crs_wkt = pyproj.CRS.from_epsg(32643).to_wkt()
        pyogrio.raw.write(
            str(shp_path),
            geometry=geometries,
            field_data=field_data,
            fields=fields,
            geometry_type="Polygon",
            crs=crs_wkt,
        )

        zip_dest = SAMPLE_DIR / "parcels_utm43n.zip"
        _zip_directory(Path(td), zip_dest)
        print(f"Generated {zip_dest}")


# 3. Generate roads_4326.zip (LineString shapefile in EPSG:4326)
def generate_roads_4326() -> None:
    with tempfile.TemporaryDirectory() as td:
        shp_path = Path(td) / "roads_4326.shp"

        line1 = LineString([(73.78, 19.99), (73.79, 20.00), (73.81, 20.01)])
        line2 = LineString([(73.75, 19.95), (73.77, 19.98)])

        geometries = np.array([shapely.to_wkb(line1), shapely.to_wkb(line2)], dtype=object)
        field_data = [
            np.array(["NH 848", "Gangapur Road"], dtype=object),
            np.array(["Highway", "Arterial"], dtype=object),
        ]
        fields = ["road_name", "category"]

        crs_wkt = pyproj.CRS.from_epsg(4326).to_wkt()
        pyogrio.raw.write(
            str(shp_path),
            geometry=geometries,
            field_data=field_data,
            fields=fields,
            geometry_type="LineString",
            crs=crs_wkt,
        )

        zip_dest = SAMPLE_DIR / "roads_4326.zip"
        _zip_directory(Path(td), zip_dest)
        print(f"Generated {zip_dest}")


# 4. Generate mixed_geometries.zip (Multi-layer archive with points, lines, polygons)
def generate_mixed_geometries() -> None:
    with tempfile.TemporaryDirectory() as td:
        crs_wkt = pyproj.CRS.from_epsg(4326).to_wkt()

        # 4.1 Points layer
        pt_path = Path(td) / "sensors.shp"
        pt_geoms = np.array([shapely.to_wkb(Point(73.80, 20.00))], dtype=object)
        pyogrio.raw.write(
            str(pt_path),
            geometry=pt_geoms,
            field_data=[np.array(["Sensor A"], dtype=object)],
            fields=["name"],
            geometry_type="Point",
            crs=crs_wkt,
        )

        # 4.2 Lines layer
        line_path = Path(td) / "powerlines.shp"
        line_geoms = np.array(
            [shapely.to_wkb(LineString([(73.78, 19.98), (73.82, 20.02)]))], dtype=object
        )
        pyogrio.raw.write(
            str(line_path),
            geometry=line_geoms,
            field_data=[np.array(["Line 11kV"], dtype=object)],
            fields=["line_id"],
            geometry_type="LineString",
            crs=crs_wkt,
        )

        # 4.3 Polygons layer
        poly_path = Path(td) / "reserves.shp"
        poly1 = Polygon(
            [(73.75, 19.95), (73.77, 19.95), (73.77, 19.97), (73.75, 19.97), (73.75, 19.95)]
        )
        poly_geoms = np.array([shapely.to_wkb(poly1)], dtype=object)
        pyogrio.raw.write(
            str(poly_path),
            geometry=poly_geoms,
            field_data=[np.array(["Forest Reserve"], dtype=object)],
            fields=["reserve_na"],
            geometry_type="Polygon",
            crs=crs_wkt,
        )

        zip_dest = SAMPLE_DIR / "mixed_geometries.zip"
        _zip_directory(Path(td), zip_dest)
        print(f"Generated {zip_dest}")


# 5. Generate no_prj.zip (Shapefile without .prj in geographic range)
def generate_no_prj() -> None:
    with tempfile.TemporaryDirectory() as td:
        shp_path = Path(td) / "survey_unprojected.shp"

        poly = Polygon(
            [(73.78, 19.98), (73.80, 19.98), (73.80, 20.00), (73.78, 20.00), (73.78, 19.98)]
        )
        geometries = np.array([shapely.to_wkb(poly)], dtype=object)
        field_data = [np.array(["Field 1"], dtype=object)]
        fields = ["name"]

        pyogrio.raw.write(
            str(shp_path),
            geometry=geometries,
            field_data=field_data,
            fields=fields,
            geometry_type="Polygon",
            crs=None,  # No CRS written
        )

        # Delete .prj if it was created
        prj = Path(td) / "survey_unprojected.prj"
        if prj.exists():
            prj.unlink()

        zip_dest = SAMPLE_DIR / "no_prj.zip"
        _zip_directory(Path(td), zip_dest)
        print(f"Generated {zip_dest}")


# 6. Generate nested_folder.zip (Shapefile inside a subfolder inside ZIP)
def generate_nested_folder() -> None:
    with tempfile.TemporaryDirectory() as td:
        shp_path = Path(td) / "nested_parcels.shp"

        poly = Polygon(
            [(73.78, 19.98), (73.80, 19.98), (73.80, 20.00), (73.78, 20.00), (73.78, 19.98)]
        )
        geometries = np.array([shapely.to_wkb(poly)], dtype=object)
        field_data = [np.array(["Nested Plot"], dtype=object)]
        fields = ["name"]

        crs_wkt = pyproj.CRS.from_epsg(4326).to_wkt()
        pyogrio.raw.write(
            str(shp_path),
            geometry=geometries,
            field_data=field_data,
            fields=fields,
            geometry_type="Polygon",
            crs=crs_wkt,
        )

        zip_dest = SAMPLE_DIR / "nested_folder.zip"
        _zip_directory(Path(td), zip_dest, prefix="survey_data_folder")
        print(f"Generated {zip_dest}")


# 7. Generate intentionally bad files for testing
def generate_bad_files() -> None:
    # 7.1 corrupt.zip
    corrupt_dest = SAMPLE_DIR / "corrupt.zip"
    corrupt_dest.write_bytes(b"PK\x03\x04not_a_valid_zip_payload_bytes_corruption")
    print(f"Generated {corrupt_dest}")

    # 7.2 missing_shx.zip (has .shp and .dbf but missing .shx)
    with tempfile.TemporaryDirectory() as td:
        shp = Path(td) / "incomplete.shp"
        dbf = Path(td) / "incomplete.dbf"
        shp.write_bytes(b"\x00" * 100)
        dbf.write_bytes(b"\x00" * 100)
        _zip_directory(Path(td), SAMPLE_DIR / "missing_shx.zip")
    print(f"Generated {SAMPLE_DIR / 'missing_shx.zip'}")

    # 7.3 bad.kml (Malformed XML)
    bad_kml = SAMPLE_DIR / "bad.kml"
    bad_kml.write_text("<kml><Document><unclosed_tag>broken</Document></kml>")
    print(f"Generated {bad_kml}")

    # 7.4 xxe.kml (XXE entity injection attack payload)
    xxe_kml = SAMPLE_DIR / "xxe.kml"
    xxe_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE kml [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>&xxe;</name>
  </Document>
</kml>
"""
    xxe_kml.write_text(xxe_content)
    print(f"Generated {xxe_kml}")

    # 7.5 wrong_extension.kml (PNG image with .kml extension)
    png_as_kml = SAMPLE_DIR / "wrong_extension.kml"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    png_as_kml.write_bytes(png_bytes)
    print(f"Generated {png_as_kml}")

    # 7.6 empty.zip
    empty_zip = SAMPLE_DIR / "empty.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    empty_zip.write_bytes(buf.getvalue())
    print(f"Generated {empty_zip}")


if __name__ == "__main__":
    print("Generating comprehensive sample files...")
    generate_plots_kml()
    generate_parcels_utm43n()
    generate_roads_4326()
    generate_mixed_geometries()
    generate_no_prj()
    generate_nested_folder()
    generate_bad_files()
    print("All sample files successfully generated in samples/ directory.")
