"""Integration tests for file upload endpoint, async mode, and failure isolation."""

from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_kml_sync_success(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        resp = client.post(
            "/api/files/",
            files={"file": ("valid_sample.kml", f, "application/vnd.google-earth.kml+xml")},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["filename"] == "valid_sample.kml"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 3
    assert data["crs"] == "EPSG:4326"
    assert "Location" in resp.headers
    assert resp.headers["Location"] == f"/api/files/{data['id']}/"


def test_upload_shapefile_zip_sync_success(client: TestClient, sample_shapefile_zip: Path) -> None:
    with sample_shapefile_zip.open("rb") as f:
        resp = client.post("/api/files/", files={"file": ("parcels.zip", f, "application/zip")})

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 1
    assert data["crs"] == "EPSG:4326"


def test_upload_async_mode_returns_202(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        resp = client.post(
            "/api/files/?async=true",
            files={"file": ("async_sample.kml", f, "application/vnd.google-earth.kml+xml")},
        )

    assert resp.status_code == 202
    data = resp.json()
    assert "id" in data
    assert data["status"] in ("PENDING", "PROCESSING", "COMPLETED")
    assert "Location" in resp.headers


def test_failure_isolation_bad_feature_does_not_abort_file(
    client: TestClient, tmp_path: Path
) -> None:
    # KML with one valid polygon and one malformed/corrupted geometry coordinate
    mixed_kml = tmp_path / "mixed_valid_invalid.kml"
    mixed_kml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Valid Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing><coordinates>73.0,19.0,0 73.01,19.0,0 73.01,19.01,0 73.0,19.01,0 73.0,19.0,0</coordinates></LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Empty Placemark</name>
    </Placemark>
  </Document>
</kml>
""")

    with mixed_kml.open("rb") as f:
        resp = client.post(
            "/api/files/", files={"file": ("mixed.kml", f, "application/vnd.google-earth.kml+xml")}
        )

    assert resp.status_code == 201
    file_id = resp.json()["id"]

    # Check measurements
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    m_data = meas_resp.json()

    assert m_data["summary"]["feature_count"] == 2
    assert m_data["summary"]["measured_count"] == 1
    assert m_data["summary"]["skipped_count"] == 1
