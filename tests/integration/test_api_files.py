"""Integration tests for file metadata inspection, listing, and deletion."""

from pathlib import Path

from fastapi.testclient import TestClient


def test_get_file_info_exact_schema_shape(client: TestClient, sample_kml_path: Path) -> None:
    # Upload first
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files/",
            files={"file": ("test_survey.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    file_id = up_resp.json()["id"]

    # Request file metadata
    resp = client.get(f"/api/files/{file_id}/")
    assert resp.status_code == 200
    data = resp.json()

    # VERBATIM MANDATORY SPECIFICATION FIELDS
    assert "id" in data
    assert "filename" in data
    assert "feature_count" in data
    assert "crs" in data
    assert "status" in data

    assert data["id"] == file_id
    assert data["filename"] == "test_survey.kml"
    assert data["feature_count"] == 3
    assert data["crs"] == "EPSG:4326"
    assert data["status"] == "COMPLETED"


def test_list_files_and_pagination(client: TestClient, sample_kml_path: Path) -> None:
    # List files
    resp = client.get("/api/files/?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


def test_non_trailing_slash_route_alias(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files", files={"file": ("alias.kml", f, "application/vnd.google-earth.kml+xml")}
        )
    assert up_resp.status_code == 201
    file_id = up_resp.json()["id"]

    # Hit GET without trailing slash
    get_resp = client.get(f"/api/files/{file_id}")
    assert get_resp.status_code == 200


def test_delete_file_cascade(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files/",
            files={"file": ("to_delete.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    file_id = up_resp.json()["id"]

    del_resp = client.delete(f"/api/files/{file_id}/")
    assert del_resp.status_code == 204

    # Verify 404 after deletion
    get_resp = client.get(f"/api/files/{file_id}/")
    assert get_resp.status_code == 404


def test_file_not_found_returns_404(client: TestClient) -> None:
    resp = client.get("/api/files/nonexistent_id_999/")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_delete_file_not_found_returns_404(client: TestClient) -> None:
    resp = client.delete("/api/files/nonexistent_id_999/")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_feature_not_found_returns_404(client: TestClient, sample_kml_path: Path) -> None:
    with sample_kml_path.open("rb") as f:
        up_resp = client.post(
            "/api/files/",
            files={"file": ("feat_test.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    file_id = up_resp.json()["id"]

    # Request invalid feature index
    resp = client.get(f"/api/files/{file_id}/features/9999/")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_list_files_with_status_filter(client: TestClient) -> None:
    resp = client.get("/api/files/?status=COMPLETED")
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["status"] == "COMPLETED"
