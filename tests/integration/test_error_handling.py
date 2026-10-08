"""Integration tests verifying every row in the error handling matrix and error envelopes."""

import io
import zipfile

from fastapi.testclient import TestClient


def test_error_empty_filename_422(client: TestClient) -> None:
    # Empty filename
    resp = client.post("/api/files/", files={"file": ("", io.BytesIO(b"abc"), "text/plain")})
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] in ("FILE_REQUIRED", "UNSUPPORTED_FILE_TYPE", "VALIDATION_ERROR")


def test_error_empty_file_400(client: TestClient) -> None:
    # 0 bytes file
    resp = client.post(
        "/api/files/",
        files={"file": ("empty.kml", io.BytesIO(b""), "application/vnd.google-earth.kml+xml")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPTY_FILE"


def test_error_unsupported_extension_415(client: TestClient) -> None:
    resp = client.post(
        "/api/files/",
        files={
            "file": (
                "data.geojson",
                io.BytesIO(b'{"type":"FeatureCollection"}'),
                "application/json",
            )
        },
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_error_content_mismatch_415(client: TestClient) -> None:
    # PNG disguised as .kml
    png_bytes = b"\x89PNG\r\n\x1a\nfake_png_binary"
    resp = client.post(
        "/api/files/",
        files={"file": ("fake.kml", io.BytesIO(png_bytes), "application/vnd.google-earth.kml+xml")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "CONTENT_TYPE_MISMATCH"


def test_error_corrupt_zip_422(client: TestClient) -> None:
    corrupt_bytes = b"PK\x03\x04corrupted_archive_data"
    resp = client.post(
        "/api/files/", files={"file": ("corrupt.zip", io.BytesIO(corrupt_bytes), "application/zip")}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_ARCHIVE"


def test_error_shapefile_missing_components_422(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.shp", b"dummy shp")
        # Missing test.dbf and test.shx
    buf.seek(0)

    resp = client.post("/api/files/", files={"file": ("missing_parts.zip", buf, "application/zip")})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SHAPEFILE_MISSING_COMPONENTS"


def test_error_shapefile_not_found_in_zip_422(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"no shp here")
    buf.seek(0)

    resp = client.post("/api/files/", files={"file": ("no_shp.zip", buf, "application/zip")})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SHAPEFILE_NOT_FOUND"


def test_error_invalid_kml_xml_422(client: TestClient) -> None:
    bad_kml = b"<kml><broken_tag>unclosed</kml>"
    resp = client.post(
        "/api/files/",
        files={"file": ("broken.kml", io.BytesIO(bad_kml), "application/vnd.google-earth.kml+xml")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_KML"


def test_error_kml_no_features_422(client: TestClient) -> None:
    empty_kml = b'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>'
    resp = client.post(
        "/api/files/",
        files={
            "file": ("empty.kml", io.BytesIO(empty_kml), "application/vnd.google-earth.kml+xml")
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_FEATURES"


def test_error_file_not_found_404(client: TestClient) -> None:
    resp = client.get("/api/files/nonexistent_xyz_999/")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "FILE_NOT_FOUND"
    assert "request_id" in data["error"]


def test_error_bad_query_params_422(client: TestClient) -> None:
    resp = client.get("/api/files/?limit=-5")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
