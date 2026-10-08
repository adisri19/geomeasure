"""Integration tests for measurements endpoint, filtering, precision, and single feature retrieval."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import FileStatus
from app.db.models import UploadedFile
from app.repositories.file_repository import FileRepository


def test_get_measurements_structure_and_values(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files/", files={"file": ("survey.kml", f, "application/vnd.google-earth.kml+xml")}
        )
    file_id = up_resp.json()["id"]

    resp = client.get(f"/api/files/{file_id}/measurements/?precision=2")
    assert resp.status_code == 200
    data = resp.json()

    assert data["file_id"] == file_id
    assert data["status"] == "COMPLETED"
    assert "summary" in data
    assert "pagination" in data
    assert "features" in data

    # Summary checks
    summary = data["summary"]
    assert summary["feature_count"] == 3
    assert summary["measured_count"] == 2
    assert summary["skipped_count"] == 1
    assert "total_area" in summary
    assert "hectares" in summary["total_area"]
    assert "total_length" in summary
    assert "kilometers" in summary["total_length"]

    # Feature checks
    features = data["features"]
    assert len(features) == 3

    # Polygon feature
    poly_feat = next(f for f in features if f["geometry_type"] == "Polygon")
    assert poly_feat["measurement"]["type"] == "area"
    assert poly_feat["measurement"]["status"] == "OK"
    assert poly_feat["measurement"]["area_m2"] is not None
    assert poly_feat["measurement"]["area_hectares"] is not None

    # Line feature
    line_feat = next(f for f in features if f["geometry_type"] == "LineString")
    assert line_feat["measurement"]["type"] == "length"
    assert line_feat["measurement"]["status"] == "OK"
    assert line_feat["measurement"]["length_m"] is not None

    # Point feature
    point_feat = next(f for f in features if f["geometry_type"] == "Point")
    assert point_feat["measurement"]["type"] == "none"
    assert point_feat["measurement"]["status"] == "NOT_REQUIRED"


def test_measurements_geometry_type_filter(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files/",
            files={"file": ("filter_test.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    file_id = up_resp.json()["id"]

    resp = client.get(f"/api/files/{file_id}/measurements/?geometry_type=Polygon")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["features"]) == 1
    assert data["features"][0]["geometry_type"] == "Polygon"


def test_measurements_exclude_geometry(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files/",
            files={"file": ("no_geom.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    file_id = up_resp.json()["id"]

    resp = client.get(f"/api/files/{file_id}/measurements/?include_geometry=false")
    assert resp.status_code == 200
    data = resp.json()
    for feat in data["features"]:
        assert feat["geometry"] is None


def test_get_single_feature_by_index(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files/",
            files={"file": ("single_feat.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    file_id = up_resp.json()["id"]

    resp = client.get(f"/api/files/{file_id}/features/0/")
    assert resp.status_code == 200
    feat = resp.json()
    assert feat["feature_index"] == 0
    assert "measurement" in feat


def test_measurements_not_ready_conflict_409(client: TestClient, db_session: Session) -> None:
    # Insert a dummy record in PROCESSING state
    file_rec = UploadedFile(
        id="busy_file_123",
        filename="busy.kml",
        file_type="KML",
        size_bytes=100,
        sha256="fake_hash",
        feature_count=0,
        crs="EPSG:4326",
        status=FileStatus.PROCESSING.value,
        warnings=[],
        layer_names=[],
    )
    FileRepository.create_file(db_session, file_rec)

    resp = client.get("/api/files/busy_file_123/measurements/")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "FILE_NOT_READY"


def test_measurements_failed_file_422(client: TestClient, db_session: Session) -> None:
    file_rec = UploadedFile(
        id="failed_file_123",
        filename="fail.kml",
        file_type="KML",
        size_bytes=100,
        sha256="fake_hash",
        feature_count=0,
        crs="EPSG:4326",
        status=FileStatus.FAILED.value,
        error_message="Corrupted coordinates detected",
        error_code="INVALID_KML",
        warnings=[],
        layer_names=[],
    )
    FileRepository.create_file(db_session, file_rec)

    resp = client.get("/api/files/failed_file_123/measurements/")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PROCESSING_FAILED"
