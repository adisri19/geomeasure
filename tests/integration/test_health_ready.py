"""Integration tests for health and readiness probes."""

import pytest
from fastapi.testclient import TestClient


def test_health_liveness_200(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}

    # Also at /api/health
    resp_api = client.get("/api/health")
    assert resp_api.status_code == 200
    assert resp_api.json() == {"status": "healthy"}


def test_ready_probe_200(client: TestClient) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] is True
    assert data["checks"]["gdal_drivers"] is True


def test_ready_probe_db_failure_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:

    from sqlalchemy.orm import Session

    def mock_execute(*args, **kwargs):
        raise RuntimeError("Database connection timed out")

    monkeypatch.setattr(Session, "execute", mock_execute)
    resp = client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"] is False


def test_ready_probe_gdal_drivers_missing_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pyogrio

    # Mock list_drivers to return empty dict
    monkeypatch.setattr(pyogrio, "list_drivers", lambda: {})
    resp = client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["gdal_drivers"] is False
