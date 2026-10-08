"""Pytest fixtures providing synthetic test files, test database session, and API test client."""

import zipfile
from collections.abc import Generator
from pathlib import Path

import numpy as np
import pyogrio.raw
import pyproj
import pytest
import shapely
from fastapi.testclient import TestClient
from shapely.geometry import Polygon
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.db import session as db_session_mod
from app.db.base import Base
from app.main import app as fastapi_app
from app.services import upload_service as upload_service_mod

# Temporary test database file
TEST_DB_PATH = Path("./test_suite.db")
test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch global SessionLocal in app modules to point to test_engine
db_session_mod.SessionLocal = TestingSessionLocal  # type: ignore[assignment]
upload_service_mod.SessionLocal = TestingSessionLocal  # type: ignore[assignment]


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    """Create database tables once for the test session and clean up file upon exit."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture(autouse=True)
def clean_tables() -> Generator[None, None, None]:
    """Clean tables between tests to ensure test isolation."""
    yield
    with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a clean session per test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide FastAPI TestClient wired to the test database session."""

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def sample_kml_path(tmp_path: Path) -> Path:
    """Generate a valid multi-feature KML file with Polygon, LineString, and Point."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Test Document</name>
    <Folder>
      <name>Parcels</name>
      <Placemark>
        <name>Plot Alpha</name>
        <description>Test agricultural plot</description>
        <ExtendedData>
          <Data name="crop"><value>Wheat</value></Data>
        </ExtendedData>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                73.7800,19.9900,0
                73.7900,19.9900,0
                73.7900,20.0000,0
                73.7800,20.0000,0
                73.7800,19.9900,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
      <Placemark>
        <name>Access Road</name>
        <LineString>
          <coordinates>
            73.7800,19.9900,0
            73.7900,20.0000,0
          </coordinates>
        </LineString>
      </Placemark>
      <Placemark>
        <name>Well Point</name>
        <Point>
          <coordinates>73.7850,19.9950,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    file_path = tmp_path / "valid_sample.kml"
    file_path.write_text(kml_content)
    return file_path


@pytest.fixture
def sample_shapefile_zip(tmp_path: Path) -> Path:
    """Generate a valid Shapefile .zip archive in EPSG:4326."""
    shp_dir = tmp_path / "shp_src"
    shp_dir.mkdir()
    shp_file = shp_dir / "parcels.shp"

    poly = Polygon([(73.78, 19.98), (73.80, 19.98), (73.80, 20.00), (73.78, 20.00), (73.78, 19.98)])
    geometries = np.array([shapely.to_wkb(poly)], dtype=object)
    field_data = [np.array(["Plot 101"], dtype=object)]
    fields = ["name"]

    crs_wkt = pyproj.CRS.from_epsg(4326).to_wkt()
    pyogrio.raw.write(
        str(shp_file),
        geometry=geometries,
        field_data=field_data,
        fields=fields,
        geometry_type="Polygon",
        crs=crs_wkt,
    )

    zip_path = tmp_path / "parcels_4326.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in shp_dir.iterdir():
            zf.write(f, f.name)

    return zip_path


@pytest.fixture
def projected_utm_shapefile_zip(tmp_path: Path) -> Path:
    """Generate a shapefile already in projected UTM Zone 43N (EPSG:32643)."""
    shp_dir = tmp_path / "utm_src"
    shp_dir.mkdir()
    shp_file = shp_dir / "parcels_utm.shp"

    # 100m x 100m square = exactly 10,000 m2
    poly = Polygon(
        [
            (580000.0, 2210000.0),
            (580100.0, 2210000.0),
            (580100.0, 2210100.0),
            (580000.0, 2210100.0),
            (580000.0, 2210000.0),
        ]
    )
    geometries = np.array([shapely.to_wkb(poly)], dtype=object)
    field_data = [np.array(["Exact 10k m2"], dtype=object)]
    fields = ["name"]

    crs_wkt = pyproj.CRS.from_epsg(32643).to_wkt()
    pyogrio.raw.write(
        str(shp_file),
        geometry=geometries,
        field_data=field_data,
        fields=fields,
        geometry_type="Polygon",
        crs=crs_wkt,
    )

    zip_path = tmp_path / "parcels_utm.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in shp_dir.iterdir():
            zf.write(f, f.name)

    return zip_path
