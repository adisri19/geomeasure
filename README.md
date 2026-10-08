<div align="center">

# geomeasure

**Production-grade Geospatial File Measurement API in FastAPI**  
*Ingests Shapefile archives and KML documents, extracts multi-layer features, and computes projected metric area and length measurements with geodesic cross-validation.*

[![CI Pipeline](https://github.com/adisri19/geomeasure/actions/workflows/ci.yml/badge.svg)](https://github.com/adisri19/geomeasure/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen.svg)](https://github.com/adisri19/geomeasure)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/framework-FastAPI%200.115+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type%20checked-mypy%20strict-blue.svg)](https://mypy-lang.org/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)

</div>

---

`geomeasure` is a backend service built with FastAPI, pyogrio (C-level GDAL bindings), Shapely 2.0, and PyProj. It accepts geospatial vector archives (ESRI Shapefile `.zip` and KML `.kml`), normalizes geometries across heterogeneous folders and layers, and extracts every feature with its identifier, geometry type, coordinate system, and attributes. The engine strictly avoids measuring in angular degrees by dynamically reprojecting geographic coordinates to mathematically optimal metric coordinate systems (UTM, UPS, or custom Lambert Azimuthal Equal-Area) while simultaneously cross-validating results against ellipsoidal WGS 84 geodesics.

### Highlights
- **Mathematical Rigor (Never in Degrees):** Re-projects angular coordinates (`EPSG:4326`) to metric coordinate reference systems, reroutes distorting Web Mercator (`EPSG:3857`), and normalizes linear units (feet to meters).
- **Dual-Engine Auditability:** Planar projected measurements are cross-checked against ellipsoidal geodesic calculations (`pyproj.Geod(ellps="WGS84")`), reporting differences exceeding the tolerance threshold.
- **Enterprise Archive Security:** Defends against Zip-Slip path traversal, Zip-Bomb decompression traps, password-protected archives, and XML External Entity (XXE) injection attacks via hardened `defusedxml`.
- **Failure Isolation:** Feature processing is isolated with per-feature error handling, ensuring a single invalid or degenerate geometry never fails an entire file.
- **Vectorized Performance:** Benchmarked at **12,400+ features/sec** with batch database persistence and cached PROJ transformations.
- **High Test Quality:** 83 tests achieving **90% line coverage** across unit, integration, security, accuracy, and property-based test suites.
- **Production Packaging:** Multi-stage non-root Dockerfile, healthchecks, Alembic migrations, and automated GitHub Actions CI pipeline.

<div align="center">

![Architecture Pipeline](docs/assets/architecture.svg)
*Figure 1: High-level ingestion, projection, measurement, and persistence pipeline.*

</div>

---

## Table of Contents
- [1. Quick Start (60 seconds)](#1-quick-start-60-seconds)
- [2. Requirements Mapping](#2-requirements-mapping)
- [3. Setup & Installation](#3-setup--installation)
- [4. API Reference](#4-api-reference)
- [5. Architecture](#5-architecture)
- [6. Design Decisions (ADRs)](#6-design-decisions-adrs)
- [7. Testing & Quality](#7-testing--quality)
- [8. Performance & Benchmarks](#8-performance--benchmarks)
- [9. Security Considerations](#9-security-considerations)
- [10. Limitations & Known Edge Cases](#10-limitations--known-edge-cases)
- [11. Learnings](#11-learnings)
- [12. Future Scope](#12-future-scope)
- [13. Project Info](#13-project-info)

---

## 1. Quick Start (60 seconds)

### Option A: Docker (Recommended)
No local GIS libraries or Python installation required:

```bash
# 1. Start the containerized service
docker compose up -d --build

# 2. Upload a sample KML file and measure
curl -s -X POST http://localhost:8000/api/files/ \
  -F "file=@samples/plots_4326.kml" | jq .
```

### Option B: Local Python
```bash
# 1. Create virtualenv and install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Apply migrations and start the server
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# 3. Upload a sample Shapefile archive
curl -s -X POST http://localhost:8000/api/files/ \
  -F "file=@samples/parcels_utm43n.zip" | jq .
```

Open **[http://localhost:8000/docs](http://localhost:8000/docs)** to test all endpoints interactively in your browser. Sample datasets are located in `samples/` (for example, `samples/plots_4326.kml` and `samples/parcels_utm43n.zip`).

---

## 2. Requirements Mapping

The following matrix maps every requirement from the assignment brief directly to its implementation and automated tests:

| Requirement | Status | Implementation | Test |
|:---|:---:|:---|:---|
| **FastAPI Backend Framework** | Complete | [app/main.py](app/main.py), [app/api/router.py](app/api/router.py) | [tests/integration/test_health_ready.py](tests/integration/test_health_ready.py) |
| **`POST /api/files/` Upload (.zip Shapefile & .kml)** | Complete | [app/api/routes/files.py](app/api/routes/files.py#L161) | [tests/integration/test_api_upload.py](tests/integration/test_api_upload.py#L11) |
| **Per-Feature Extraction (ID, geom type, geometry, CRS, props)** | Complete | [app/services/readers/shapefile_reader.py](app/services/readers/shapefile_reader.py), [app/services/readers/kml_reader.py](app/services/readers/kml_reader.py) | [tests/unit/test_shapefile_reader.py](tests/unit/test_shapefile_reader.py#L15), [tests/unit/test_kml_reader.py](tests/unit/test_kml_reader.py#L11) |
| **Graceful Handling of Unsupported Geometries** | Complete | [app/services/measurement_service.py](app/services/measurement_service.py#L50) | [tests/integration/test_api_upload.py](tests/integration/test_api_upload.py#L57), [tests/unit/test_measurement_service.py](tests/unit/test_measurement_service.py#L167) |
| **Polygon Area / LineString Length / Point None** | Complete | [app/services/measurement_service.py](app/services/measurement_service.py#L72) | [tests/unit/test_measurement_service.py](tests/unit/test_measurement_service.py#L20), [tests/unit/test_measurement_service.py](tests/unit/test_measurement_service.py#L49) |
| **No Measurement in Degrees; Projected Metric CRS** | Complete | [app/services/crs_service.py](app/services/crs_service.py#L102) | [tests/unit/test_crs_service.py](tests/unit/test_crs_service.py#L39), [tests/unit/test_crs_service.py](tests/unit/test_crs_service.py#L74) |
| **`GET /api/files/{id}/` Exact Minimal Schema** | Complete | [app/schemas/file.py](app/schemas/file.py#L11), [app/api/routes/files.py](app/api/routes/files.py#L227) | [tests/integration/test_api_files.py](tests/integration/test_api_files.py#L7) |
| **`GET /api/files/{id}/measurements/` Endpoint** | Complete | [app/api/routes/files.py](app/api/routes/files.py#L290), [app/schemas/feature.py](app/schemas/feature.py#L40) | [tests/integration/test_api_measurements.py](tests/integration/test_api_measurements.py#L12) |
| **README: Setup, API, Architecture, Decisions** | Complete | [README.md](README.md), [docs/crs-strategy.md](docs/crs-strategy.md), [docs/architecture.md](docs/architecture.md) | Verified by documentation audit |
| **README: Learnings and Future Scope** | Complete | [README.md #11](README.md#11-learnings), [README.md #12](README.md#12-future-scope) | Verified by documentation audit |
| **Public GitHub Repository & Hygiene** | Complete | Conventional commits, git tags, MIT license | [CHANGELOG.md](CHANGELOG.md), [LICENSE](LICENSE) |

---

## 3. Setup & Installation

### Prerequisites
- Python 3.11 or 3.12
- Docker 24+ and Docker Compose v2 (optional)
- Standard binary wheels for `pyogrio` bundle GDAL C-libraries on Linux and macOS. If building from source, install system headers:
  - **Debian / Ubuntu:** `sudo apt-get install -y libgdal-dev gdal-bin libgeos-dev libproj-dev`
  - **macOS:** `brew install gdal geos proj`

### Step-by-Step Installation

#### Using standard venv + pip
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
```

#### Using `uv`
```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
```

### Environment Variables
All settings are configured via environment variables or a local `.env` file (`app/core/config.py`):

| Variable | Default | Description | Example |
|:---|:---|:---|:---|
| `DATABASE_URL` | `sqlite:///./geomeasure.db` | SQLAlchemy connection string | `postgresql://user:pass@localhost:5432/geodb` |
| `UPLOAD_DIR` | `./uploads` | Spool directory for file processing | `/var/tmp/geomeasure/uploads` |
| `MAX_UPLOAD_MB` | `50` | Maximum upload size in megabytes | `100` |
| `MAX_UNCOMPRESSED_MB` | `250` | Maximum uncompressed ZIP extraction size | `500` |
| `MAX_ZIP_ENTRIES` | `250` | Maximum entry count allowed in an archive | `500` |
| `MAX_COMPRESSION_RATIO` | `50.0` | Zip-bomb ratio defense threshold | `40.0` |
| `GEODESIC_TOLERANCE_PCT`| `0.5` | Discrepancy threshold (%) triggering warning note | `1.0` |
| `DEFAULT_PAGE_SIZE` | `100` | Default feature pagination limit | `50` |
| `MAX_PAGE_SIZE` | `1000` | Maximum permissible feature pagination limit | `2000` |
| `LOG_LEVEL` | `INFO` | Logging verbosity | `DEBUG` |
| `ENVIRONMENT` | `development` | Deployment environment | `production` |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated) | `https://app.example.com` |
| `ENABLE_ASYNC_MODE` | `True` | Enable background task execution (`?async=true`) | `True` |

### Developer Commands (`Makefile`)
| Target | Description |
|:---|:---|
| `make install` | Create virtualenv and install all dependencies |
| `make dev` | Run development server with auto-reload on `:8000` |
| `make run` | Run production-style Uvicorn server |
| `make test` | Run full Pytest test suite |
| `make cov` | Run tests with terminal coverage and HTML report |
| `make lint` | Run Ruff linter and formatting checks |
| `make format` | Auto-format codebase using Ruff |
| `make typecheck` | Run static type checking using Mypy in strict mode |
| `make migrate` | Apply database migrations via Alembic |
| `make samples` | Regenerate synthetic and test datasets in `samples/` |
| `make openapi` | Export OpenAPI 3.1 schema to `docs/openapi.json` |
| `make docker-build` | Build production multi-stage Docker container |
| `make docker-run` | Launch containerized service via Docker Compose |
| `make smoke` | Execute automated curl smoke test suite |
| `make clean` | Clean build artifacts, pycache, and test databases |
| `make all` | Execute full verification pipeline (`lint` + `typecheck` + `cov`) |

### Troubleshooting
| Issue | Cause | Resolution |
|:---|:---|:---|
| `Driver not found: KML` | GDAL missing KML/LIBKML driver | Use bundled `pyogrio` wheels or install `gdal-bin` via apt/brew |
| `Address already in use: 8000` | Port collision | Pass alternative port: `uvicorn app.main:app --port 8080` |
| `SQLite database is locked` | High write concurrency | SQLite is configured in WAL mode; for high concurrency, point `DATABASE_URL` to PostgreSQL |
| `413 FILE_TOO_LARGE` | Upload exceeds 50 MB | Increase `MAX_UPLOAD_MB=100` in `.env` |
| `422 CRS_UNDEFINED` | Shapefile lacks `.prj` and coordinates are projected | Export shapefile with valid `.prj` or geographic coordinates |
| `Permission denied: /app/data` | Container volume permissions | Dockerfile runs as `appuser:appgroup` (UID 1000); verify host volume ownership |

---

## 4. API Reference

All requests and responses use JSON. Dual route registration ensures both trailing slash (`/api/files/`) and bare URLs (`/api/files`) work without dropping multipart bodies. Complete worked request/response documentation is available in [docs/api-examples.md](docs/api-examples.md).

### 4.1 POST `/api/files/` — Upload and Process File
Uploads a Shapefile archive (`.zip`) or KML document (`.kml`) for validation, projection, and measurement.

**Parameters:**
| Parameter | Location | Type | Required | Default | Description |
|:---|:---|:---|:---:|:---:|:---|
| `file` | `formData` | `UploadFile` | Yes | — | Geospatial archive (`.zip`) or KML document (`.kml`) |
| `async` | `query` | `boolean` | No | `false` | When `true`, returns `202 Accepted` and processes via background tasks |

**Request (curl):**
```bash
curl -i -X POST http://localhost:8000/api/files/ \
  -F "file=@samples/plots_4326.kml"
```

<details>
<summary><strong>Success Response (<code>201 Created</code>)</strong></summary>

```http
HTTP/1.1 201 Created
Location: /api/files/26875053bf12/
X-Request-ID: req-b98a3910c2
Content-Type: application/json
```
```json
{
  "id": "26875053bf12",
  "filename": "plots_4326.kml",
  "feature_count": 5,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "file_type": "KML",
  "size_bytes": 3014,
  "sha256": "69dec06e63c3bec56a3387460e7d906df177d406c9dba046cf933ff6955a5ecd",
  "geometry_type_counts": {
    "LineString": 1,
    "None": 1,
    "Point": 1,
    "Polygon": 2
  },
  "crs_assumed": false,
  "warnings": [],
  "error": null,
  "created_at": "2026-10-08T22:48:02",
  "processed_at": "2026-10-08T22:48:02.124891Z",
  "processing_ms": 18.42,
  "links": {
    "self": "/api/files/26875053bf12/",
    "measurements": "/api/files/26875053bf12/measurements/"
  }
}
```
</details>

---

### 4.2 GET `/api/files/{id}/` — File Information
Retrieves metadata and status for an uploaded file. Strictly returns the shape required by the hiring brief.

**Request (curl):**
```bash
curl -s http://localhost:8000/api/files/26875053bf12/ | jq .
```

<details>
<summary><strong>Success Response (<code>200 OK</code>)</strong></summary>

```json
{
  "id": "26875053bf12",
  "filename": "plots_4326.kml",
  "feature_count": 5,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "file_type": "KML",
  "size_bytes": 3014,
  "sha256": "69dec06e63c3bec56a3387460e7d906df177d406c9dba046cf933ff6955a5ecd",
  "geometry_type_counts": {
    "LineString": 1,
    "None": 1,
    "Point": 1,
    "Polygon": 2
  },
  "crs_assumed": false,
  "warnings": [],
  "error": null,
  "created_at": "2026-10-08T22:48:02",
  "processed_at": "2026-10-08T22:48:02.124891Z",
  "processing_ms": 18.42,
  "links": {
    "self": "/api/files/26875053bf12/",
    "measurements": "/api/files/26875053bf12/measurements/"
  }
}
```
</details>

---

### 4.3 GET `/api/files/{id}/measurements/` — Feature Measurements
Retrieves computed area and length measurements, aggregates, and pagination metadata.

**Parameters:**
| Parameter | Location | Type | Required | Default | Description |
|:---|:---|:---|:---:|:---:|:---|
| `file_id` | `path` | `string` | Yes | — | Unique file identifier |
| `limit` | `query` | `integer` | No | `100` | Number of features to return (min: 1, max: 1000) |
| `offset` | `query` | `integer` | No | `0` | Pagination offset |
| `geometry_type` | `query` | `string` | No | `null` | Optional geometry filter (`Polygon`, `LineString`, `Point`) |
| `include_geometry` | `query` | `boolean` | No | `true` | Include GeoJSON geometry objects in response |
| `precision` | `query` | `integer` | No | `4` | Number of decimal places for numeric outputs |

**Request (curl):**
```bash
curl -s "http://localhost:8000/api/files/26875053bf12/measurements/?limit=2&precision=2" | jq .
```

<details>
<summary><strong>Success Response (<code>200 OK</code>)</strong></summary>

```json
{
  "file_id": "26875053bf12",
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "summary": {
    "feature_count": 5,
    "measured_count": 3,
    "skipped_count": 2,
    "total_area": {
      "square_meters": 6566544.09,
      "hectares": 656.65,
      "square_kilometers": 6.57,
      "acres": 1622.63
    },
    "total_length": {
      "meters": 8386.6,
      "kilometers": 8.39,
      "miles": 5.21
    },
    "geometry_type_counts": {
      "LineString": 1,
      "None": 1,
      "Point": 1,
      "Polygon": 2
    }
  },
  "pagination": {
    "limit": 2,
    "offset": 0,
    "total": 5,
    "next": "/api/files/26875053bf12/measurements/?limit=2&offset=2",
    "previous": null
  },
  "features": [
    {
      "feature_index": 0,
      "id": "plot_nashik_01",
      "layer_name": "Parcels",
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [[73.78, 19.99], [73.8, 19.99], [73.8, 20.01], [73.78, 20.01], [73.78, 19.99]],
          [[73.785, 19.995], [73.795, 19.995], [73.795, 20.005], [73.785, 20.005], [73.785, 19.995]]
        ]
      },
      "properties": {
        "name": "Nashik Vineyard Estate",
        "crop": "Grapes",
        "soil_type": "Black Cotton"
      },
      "measurement": {
        "type": "area",
        "status": "OK",
        "area_m2": 3474060.63,
        "area_hectares": 347.41,
        "area_acres": 858.46,
        "area_sq_km": 3.47,
        "perimeter_m": 12918.47,
        "length_m": null,
        "length_km": null,
        "length_miles": null,
        "geodesic_area_m2": 5792440.6,
        "geodesic_length_m": null,
        "method": "UTM Zone 43N (EPSG:32643)",
        "projected_crs": "EPSG:32643",
        "note": "Projected area differs from ellipsoidal geodesic by 40.02% (tolerance 0.5%)"
      }
    }
  ]
}
```
</details>

---

### Response Field Dictionary
| Field | Type | Description |
|:---|:---|:---|
| `measurement.type` | `string` | Primary metric category: `area`, `length`, or `none` |
| `measurement.status` | `string` | Outcome: `OK`, `NOT_REQUIRED`, `SKIPPED_UNSUPPORTED`, `SKIPPED_EMPTY`, `SKIPPED_INVALID`, `ERROR` |
| `measurement.area_m2` | `float` | **Primary measurement:** planar area in square meters using projected CRS |
| `measurement.area_hectares`| `float` | Area converted to hectares ($10,000\text{ m}^2$) |
| `measurement.area_acres` | `float` | Area converted to international acres ($4,046.856\text{ m}^2$) |
| `measurement.perimeter_m` | `float` | Total boundary perimeter in meters (includes outer and inner hole boundaries) |
| `measurement.length_m` | `float` | **Primary measurement:** planar length in meters using projected CRS |
| `measurement.geodesic_area_m2` | `float` | **Audit verification:** ellipsoidal geodesic area computed via `pyproj.Geod` on WGS 84 |
| `measurement.projected_crs`| `string` | Projected CRS used for planar calculations (e.g. `EPSG:32643`) |
| `measurement.method` | `string` | Human-readable projection method (e.g. `UTM Zone 43N`, `Custom LAEA`, `Native Projected`) |
| `measurement.note` | `string` | Audit warning or topological repair explanation |

### Status Lifecycle
```mermaid
stateDiagram-v2
    [*] --> PENDING: Upload Received
    PENDING --> PROCESSING: Worker Picked Up
    PROCESSING --> COMPLETED: Features Processed & Persisted
    PROCESSING --> FAILED: Fatal Validation / Parse Error
    COMPLETED --> [*]
    FAILED --> [*]
```
*Figure 2: File ingestion lifecycle state transitions.*

---

## 5. Architecture

The application is structured into four distinct layers: Presentation, Domain/Service, Repository, and Infrastructure.

```
geospatial-measurement-api/
├── app/
│   ├── main.py                    # App factory, middlewares, exception handlers, lifespan
│   ├── core/                      # Settings, structured logging, errors, constants
│   ├── api/                       # Dependencies, routes (/api/files, /health, /ready)
│   ├── db/                        # SQLAlchemy 2.0 Base, Session, and ORM Models
│   ├── schemas/                   # Pydantic v2 validation and serialization models
│   ├── services/                  # Business logic (Readers, CRS, Measurements, Zip)
│   │   ├── readers/               # Strategy pattern parsers (Shapefile, KML, Factory)
│   │   ├── crs_service.py         # Dynamic projection selector and transformer cache
│   │   ├── geometry_service.py    # Topology repair (make_valid) & 2D flattening
│   │   ├── measurement_service.py # Planar and geodesic measurement calculators
│   │   ├── upload_service.py      # Upload workflow orchestrator
│   │   ├── zip_handler.py         # Secure zip extractor (slip & bomb defenses)
│   │   └── file_validation.py     # Content-sniffing & streaming limits
│   └── repositories/              # Database persistence abstraction (FileRepository)
├── alembic/                       # Database schema versioning and migrations
├── tests/                         # Unit, integration, and property test suites
├── samples/                       # Sample geospatial datasets
├── scripts/                       # Benchmark and automated smoke test scripts
└── docs/                          # Architectural & CRS technical guides
```

### 5.1 Processing Flow
```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Route as FastAPI Route (/api/files/)
    participant Val as File Validation Service
    participant Zip as Safe Zip Extractor
    participant Read as Reader Factory
    participant CRS as CRS Decision Engine
    participant Meas as Measurement Engine
    participant Repo as File Repository
    participant DB as SQLite / PostgreSQL

    Client->>Route: POST /api/files/ (multipart/form-data)
    Route->>Val: Stream validate bytes & check magic header
    Val-->>Route: Validated Temp File Path
    Route->>Repo: Create record (Status: PENDING)
    Repo->>DB: INSERT into uploaded_files
    
    Route->>Route: Transition to PROCESSING
    alt Shapefile (.zip)
        Route->>Zip: Extract archive with security checks (Zip-Slip, Zip-Bomb)
        Zip-->>Route: Discovered Shapefile Components
        Route->>Read: ShapefileReader.read(shp_path)
    else KML (.kml)
        Route->>Read: KmlReader.read(kml_path) with defusedxml
    end
    Read-->>Route: FileMetadata + list[RawFeature]

    loop For Every Feature (Isolated Try/Except)
        Route->>Meas: Measure RawFeature
        Meas->>CRS: select_projected_crs(geom, source_crs)
        CRS-->>Meas: ProjectedCrsDecision (UTM / UPS / LAEA / Native)
        Meas->>Meas: Reproject to metric projected CRS
        Meas->>Meas: Compute Area / Length / Perimeter
        Meas->>Meas: PyProj Geod WGS84 Cross-Validation
        Meas-->>Route: CalculatedMeasurement
    end

    Route->>Repo: Bulk insert features & update file status (COMPLETED)
    Repo->>DB: Transactional batch commit
    Route-->>Client: 201 Created + Location Header + FileInfo JSON
```
*Figure 3: End-to-end file upload and measurement sequence.*

1. **Stream Validation:** The multipart upload is validated in 64 KB chunks, enforcing file size limits without buffering unbounded memory.
2. **Format Sniffing:** Verifies ZIP magic bytes (`PK\x03\x04`) or XML `<kml>` root tags.
3. **Archive Extraction:** The ZIP extractor inspects paths to block directory traversal and verifies decompression ratios.
4. **Reader Normalization:** The selected reader parses features, strips altitude (Z), and normalizes coordinates.
5. **Dynamic Projection:** Determines the optimal projected metric CRS based on feature bounds and geometry type.
6. **Planar Measurement:** Computes metric area and perimeter for polygons, and length for lines.
7. **Geodesic Audit:** Cross-checks planar measurements against an ellipsoidal calculation using `pyproj.Geod`.
8. **Batch Persistence:** Features and summary aggregates are committed in a single database transaction.

### 5.2 Measurement Calculation Flow
```mermaid
flowchart TD
    FeatIn([Raw Feature In]) --> CleanGeom[Clean Geometry: Force 2D & Check Validity]
    CleanGeom --> ValidCheck{Is Valid?}
    ValidCheck -- No --> MakeValid[Repair via shapely.make_valid]
    ValidCheck -- Yes --> CheckType{Geometry Type?}
    MakeValid --> CheckType
    
    CheckType -- Point / MultiPoint --> PtMeasure[Set Status: NOT_REQUIRED]
    CheckType -- Empty / Null --> EmptyMeasure[Set Status: SKIPPED_EMPTY]
    CheckType -- Polygon / LineString --> SelectCRS[select_projected_crs]
    
    SelectCRS --> Reproject[Reproject Geometry to Target Metric CRS]
    Reproject --> PlanarCalc[Compute Planar Area / Length / Perimeter]
    PlanarCalc --> GeodCalc[Compute Geodesic Ground Truth via WGS84 Geod]
    GeodCalc --> ToleranceCheck{Diff > Tolerance?}
    ToleranceCheck -- Yes --> AddNote[Attach Audit Warning Note]
    ToleranceCheck -- No --> Finalize[Set Status: OK]
    AddNote --> Finalize
    
    PtMeasure --> Out([FeatureRecord Persisted])
    EmptyMeasure --> Out
    Finalize --> Out
```
*Figure 4: Per-feature measurement calculation and audit workflow.*

### 5.3 Coordinate Reference System (CRS) Strategy
Detailed technical documentation and mathematical proofs are provided in [docs/crs-strategy.md](docs/crs-strategy.md).

```mermaid
flowchart TD
    Start([Input Feature Geometry & Source CRS]) --> CheckProjected{Is Source CRS Projected?}
    
    CheckProjected -- Yes --> CheckDistort{Is Distorting?<br>e.g. Web Mercator EPSG:3857}
    CheckDistort -- No --> NativeProjected[Native Projected Measurement<br>Detect Axis Units<br>Apply Conversion Factor to SI Base]
    CheckDistort -- Yes --> ReprojectToGeo[Reproject to Geographic WGS 84]
    
    CheckProjected -- No --> CheckLat{Inspect Centroid Latitude}
    ReprojectToGeo --> CheckLat
    
    CheckLat -- |lat| >= 84° --> PolarUPS[Universal Polar Stereographic<br>UPS North: EPSG:32661<br>UPS South: EPSG:32761]
    
    CheckLat -- |lat| < 84° --> CheckSpan{Longitudinal Span <= 6°?}
    
    CheckSpan -- Yes --> UTMCalc[Calculate UTM Zone<br>Apply Norway/Svalbard Exceptions<br>North: EPSG:326xx / South: EPSG:327xx]
    CheckSpan -- No --> CustomLAEA[Custom Lambert Azimuthal Equal-Area<br>Centered at Feature Centroid<br>+proj=laea +lat_0=φ +lon_0=λ]
    
    NativeProjected --> Measure[Compute Area / Length in Meters / Square Meters]
    PolarUPS --> Measure
    UTMCalc --> Measure
    CustomLAEA --> Measure
    
    Measure --> GeodAudit[PyProj Geod WGS84 Cross-Validation<br>Compare Projected vs Geodesic<br>Audit Note if Diff > Tolerance]
    GeodAudit --> Result([Calculated Measurement Record])
```
*Figure 5: CRS projection selection decision tree.*

#### CRS Decision Cases
| Case | Input Condition | Selected Target CRS | Unit Handling | Verifying Test |
|:---|:---|:---|:---|:---|
| **Geographic Local** | `EPSG:4326`, span $\le 6^\circ$, $|\text{lat}| < 84^\circ$ | Local UTM Zone (`EPSG:32601`–`32660` / `32701`–`32760`) | Meters ($1.0$) | `test_select_projected_crs_single_utm_zone` |
| **Geographic Continental** | `EPSG:4326`, span $> 6^\circ$ | Custom Lambert Azimuthal Equal-Area (`+proj=laea`) | Meters ($1.0$) | `test_select_projected_crs_wide_extent_laea_fallback` |
| **Polar Regions** | `EPSG:4326`, $|\text{lat}| \ge 84^\circ$ | UPS North (`EPSG:32661`) or South (`EPSG:32761`) | Meters ($1.0$) | `test_select_projected_crs_polar_regions` |
| **Native Metric Projected** | Non-distorting projected CRS | Preserves native CRS | Metric ($1.0$) | `test_select_projected_crs_native_metric_passthrough` |
| **Native Foot / Survey Foot** | State Plane in feet | Preserves native projection | Multiplies by $0.3048$ / $\frac{1200}{3937}$ | `test_linear_unit_conversion_feet` |
| **Web Mercator Reroute** | `EPSG:3857` / `EPSG:900913` | Reprojected to geographic $\to$ UTM / LAEA | Meters ($1.0$) | `test_select_projected_crs_web_mercator_distortion_reroute` |
| **Missing `.prj` (Degree Bounds)**| No `.prj`, bounds $\in [-180, 180] \times [-90, 90]$ | Assumes `EPSG:4326` with explicit warning | Standard pipeline | `test_shapefile_missing_prj_assumed_geographic` |
| **Missing `.prj` (Projected)** | No `.prj`, bounds exceed degree range | Rejects upload with `422 CRS_UNDEFINED` | — | `test_shapefile_missing_prj_exceeding_geographic_raises` |

#### Why Computing in Degrees Fails
Geographic coordinates measure angular degrees on an ellipsoid. A degree of longitude shrinks with latitude by $\cos(\text{latitude})$:
- At the equator ($0^\circ$), $1^\circ$ of longitude spans $\approx 111.32\text{ km}$.
- At $60^\circ\text{ N}$, $1^\circ$ of longitude spans only $\approx 55.80\text{ km}$ ($\cos(60^\circ) = 0.5$).
- Calculating planar area in degree units treats $1^\circ \times 1^\circ$ as equal everywhere, causing a $100\%$ distortion error between the equator and $60^\circ\text{ N}$.

#### Axis Order Policy
The API enforces standard Cartesian ordering `(x, y)` / `(lon, lat)` by setting `always_xy=True` on every `pyproj.Transformer` instance, preventing axis-swap bugs introduced in PROJ 6+.

### 5.4 Data Model
Comprehensive ER diagrams and schema specifications are documented in [docs/architecture.md](docs/architecture.md).

```mermaid
erDiagram
    uploaded_files ||--o{ features : "contains (cascade delete)"

    uploaded_files {
        string id PK "Unique 12-char hex ID"
        string filename "Sanitized original filename"
        string file_type "SHAPEFILE or KML"
        int size_bytes "File size in bytes"
        string sha256 "SHA-256 content digest"
        int feature_count "Total feature records"
        string crs "Unified CRS string or MIXED"
        string crs_wkt "Full OGC WKT definition"
        boolean crs_assumed "True if heuristic was applied"
        string status "PENDING, PROCESSING, COMPLETED, FAILED"
        string error_message "Error message if FAILED"
        string error_code "Standardized error code"
        json warnings "List of non-fatal warnings"
        json layer_names "List of extracted layer names"
        float processing_ms "Processing duration in ms"
        datetime created_at "Upload timestamp"
        datetime processed_at "Completion timestamp"
    }

    features {
        int id PK "Autoincrement surrogate PK"
        string file_id FK "FK to uploaded_files.id"
        int feature_index "0-based feature index"
        string source_feature_id "FID from source file or null"
        string layer_name "Name of source layer or folder"
        string geometry_type "Point, Polygon, LineString, etc."
        json geometry "GeoJSON representation in source CRS"
        string crs "Per-feature CRS string"
        json properties "Sanitized JSON attributes"
        string measurement_type "area, length, none"
        float area_m2 "Area in square meters"
        float length_m "Length in meters"
        float perimeter_m "Perimeter in meters"
        float geodesic_area_m2 "Geodesic verification area"
        float geodesic_length_m "Geodesic verification length"
        string measurement_method "Projection or method description"
        string measurement_crs "Projected CRS used (e.g. EPSG:32643)"
        string measurement_status "OK, SKIPPED_UNSUPPORTED, etc."
        string measurement_note "Audit note or repair reason"
    }
```
*Figure 6: Entity-relationship data model.*

---

## 6. Design Decisions (ADRs)

| Decision | Chosen Architecture | Alternatives Rejected | Rationale & Trade-offs |
|:---|:---|:---|:---|
| **Framework** | **FastAPI** | Django + DRF, Flask | Native async I/O for file uploads, strict Pydantic v2 schemas, zero-overhead Swagger docs, and lower footprint than Django for a focused microservice. |
| **Geometry Storage** | **JSON / GeoJSON Text** | PostGIS `GEOMETRY` column | Allows local execution on SQLite with zero setup friction while remaining 100% compatible with PostgreSQL via standard `JSON` columns. |
| **Ingestion Execution** | **Synchronous Default** with `?async=true` Background | Celery / Redis Queue, purely async polling | Matches hiring brief's expectation of immediate status `COMPLETED`, while offloading CPU-intensive GIS transformations via `run_in_threadpool`. |
| **Projection Strategy** | **Per-Feature Dynamic UTM/LAEA** | Single global projection (e.g. World Mollweide) | Single global projections incur significant local shape/distance distortion. Per-feature UTM maintains $< 0.1\%$ local scale distortion. |
| **Geodesic Role** | **Audit / Cross-Validation Field** | Primary measurement | Brief explicitly mandates transforming to a projected metric CRS. Geodesic serves as the mathematical ground truth. |
| **Parser Engine** | **pyogrio** (C-GDAL) + **defusedxml** | Pure-python shapefile (`pyshp`), `fastkml` | `pyogrio` delivers C-level GDAL speed and handles encoding, attribute types, and projection strings natively. |
| **Missing `.prj` Policy** | **Bounding Box Heuristic** | Silent failure, or blind 4326 guess | If bounding coordinates lie within $[-180, 180] \times [-90, 90]$, assume `EPSG:4326` with an explicit warning; otherwise reject with `422 CRS_UNDEFINED`. |
| **Invalid Topology** | **`shapely.make_valid`** | `buffer(0)` or immediate rejection | `make_valid` repairs self-intersecting bowtie polygons and sliver rings without modifying valid vertex boundaries. |
| **Degenerate Geometries**| **Return 0.0 with Audit Note** | Raise 422 error | A single zero-length line or collapsed polygon must not fail processing of an entire multi-thousand feature dataset. |
| **Archive Defense** | **Stream Ratio & Canonical Path Check** | Relying on `zipfile.extractall` | Python's standard `extractall` is vulnerable to path traversal (Zip-Slip) without entry validation. |
| **URL Trailing Slashes** | **Dual Route Registration** | Strict redirect (`redirect_slashes=True`) | Direct aliases ensure HTTP clients submitting multipart bodies aren't dropped or converted to GET via 307/308 redirects. |

---

## 7. Testing & Quality

### Running Tests and Quality Checks
```bash
# Run test suite with line-by-line coverage
make cov

# Run linting and code formatting checks
make lint

# Run static type checking in strict mode
make typecheck

# Execute end-to-end smoke tests against a running server
make smoke
```

### Test Categories
| Category | Directory | Count | Scope |
|:---|:---|:---:|:---|
| **Unit Tests** | `tests/unit/` | 42 | CRS selection, UTM zones, unit scaling, readers, zip defense, geometry cleanup |
| **Integration Tests** | `tests/integration/` | 37 | End-to-end HTTP endpoints, multipart uploads, error matrix, health checks |
| **Property Tests** | `tests/property/` | 4 | Invariant testing (Hypothesis): translation invariance, scaling relationships |
| **Total Test Suite** | — | **83** | **100% Passing (0 Failures)** |

### Coverage by Module
| Module | Statements | Missing Lines | Coverage |
|:---|:---:|:---:|:---:|
| `app/api/routes/files.py` | 102 | 3 | **97%** |
| `app/api/routes/health.py` | 35 | 3 | **91%** |
| `app/repositories/file_repository.py` | 102 | 0 | **100%** |
| `app/services/crs_service.py` | 101 | 9 | **91%** |
| `app/services/file_validation.py` | 79 | 5 | **94%** |
| `app/services/geometry_service.py` | 23 | 4 | **83%** |
| `app/services/measurement_service.py` | 134 | 22 | **84%** |
| `app/services/zip_handler.py` | 97 | 9 | **91%** |
| `app/services/readers/shapefile_reader.py` | 161 | 41 | **75%** |
| `app/services/readers/kml_reader.py` | 177 | 31 | **82%** |
| **Total Engine & Services** | **1,601** | **156** | **90%** |

### Mathematical Accuracy Benchmarks
| Reference Test Shape | Native CRS | Projected Method | Measured Output | Reference Expected | Error % |
|:---|:---|:---|:---|:---|:---:|
| **$1^\circ \times 1^\circ$ Box at Equator ($0^\circ\text{ N}$)** | `EPSG:4326` | Custom LAEA | $12,322.54\text{ km}^2$ | $12,308.78\text{ km}^2$ (geodesic) | $+0.11\%$ |
| **$1^\circ \times 1^\circ$ Box at $60^\circ\text{ N}$** | `EPSG:4326` | Custom LAEA | $6,120.76\text{ km}^2$ | $6,122.94\text{ km}^2$ (geodesic) | $-0.04\%$ |
| **$1^\circ$ Longitude Line at Equator** | `EPSG:4326` | UTM Zone 31N | $111.383\text{ km}$ | $111.319\text{ km}$ (geodesic) | $+0.05\%$ |
| **$100\text{m} \times 100\text{m}$ Polygon with $20\text{m} \times 20\text{m}$ Hole** | `EPSG:32643` | Native Projected | $9,600.0\text{ m}^2$ | $9,600.0\text{ m}^2$ (exact) | $0.00\%$ |
| **Web Mercator vs EPSG:4326 Consistency** | `EPSG:3857` | Rerouted UTM | $1,158,059.9\text{ m}^2$ | $1,158,059.9\text{ m}^2$ | $0.00\%$ |

---

## 8. Performance & Benchmarks

Benchmarks were performed using `scripts/benchmark.py`. Complete methodology and system specifications are documented in [docs/benchmarks.md](docs/benchmarks.md).

```text
=== BENCHMARK RESULTS ===
Feature count:        10,000
Total time:           0.80 seconds
Throughput:           12,485.3 features / sec
Total measured area:  1,043.86 km²
Measured count:       10,000
Skipped count:        0
========================
```

### Benchmark Metrics (Apple M4, 16 GB RAM, macOS Darwin 27.0, Python 3.12.13)
| Metric | Value |
|:---|:---|
| **Synthetic Dataset Volume** | 10,000 Polygon Features |
| **Total Ingestion & Measurement Time** | **0.80 seconds** |
| **Processing Throughput** | **12,485 features / second** |
| **Per-Feature Latency** | **80 microseconds (0.08 ms)** |
| **Peak Memory Usage (RSS)** | **~78 MB** |

---

## 9. Security Considerations

| Threat Vector | Mitigation Strategy | Verifying Test Case |
|:---|:---|:---|
| **Path Traversal (Zip-Slip)** | Validates canonical target paths using `os.path.commonpath` prior to extraction. | `test_zip_slip_traversal_rejected` |
| **Zip-Bomb Denial of Service** | Caps extraction ratio ($50:1$), maximum entry count ($250$), and uncompressed size ($250\text{ MB}$). | `test_zip_bomb_excessive_entries_rejected` |
| **XML External Entity (XXE)** | Uses `defusedxml` with entity expansion and external DTD resolution disabled. | `test_kml_reader_blocks_xxe_payload` |
| **Unbounded Memory Uploads** | Enforces streaming byte chunk counters ($50\text{ MB}$ limit) without loading entire files into memory. | `test_stream_validate_exceeding_max_bytes` |
| **MIME / Content Spoofing** | Inspects magic byte signatures (`PK\x03\x04` and `<kml>`) rather than trusting extensions. | `test_sniff_content_type_mismatch` |
| **Container Privilege Escalation** | Multi-stage Docker image drops root privileges to `appuser` (UID 1000). | Verified in `Dockerfile` |

---

## 10. Limitations & Known Edge Cases

1. **Elevation Coordinates Ignored:** Geodetic altitude coordinates ($Z$) are discarded; measurements reflect 2D planar or ellipsoidal surface projections.
2. **Overlapping MultiPolygons:** Component polygons within a MultiPolygon are measured additively; overlapping intersections are not automatically unified.
3. **Antimeridian Wrapping:** Polygons crossing the $180^\circ$ meridian without pre-split boundaries may experience projection wrapping artifacts in standard projections.
4. **KML NetworkLinks:** Remote network links are not fetched dynamically to maintain offline reproducibility and prevent SSRF security risks.

---

## 11. Learnings

1. **KML Axis Ordering Pitfall:**
   *What I assumed:* KML coordinates would follow the common conversational convention (`latitude, longitude`).  
   *What actually happened:* The OGC KML standard mandates `longitude, latitude[, altitude]`. Passing coordinates directly into PROJ resulted in transposed coordinates in polar regions.  
   *What I changed:* Enforced `always_xy=True` across all `pyproj.Transformer` instances and added tests verifying coordinate order.

2. **Zip Extraction Ordering Traps:**
   *What I assumed:* Standard archive entry filtering could skip hidden files before checking for path traversal.  
   *What actually happened:* Malicious path-traversal entries like `../evil.shp` began with a dot and were skipped rather than rejected.  
   *What I changed:* Re-ordered security checks so that canonical path resolution runs before filename filtering.

3. **Web Mercator Area Distortions:**
   *What I assumed:* Web Mercator (`EPSG:3857`) could be measured natively as a projected coordinate system.  
   *What actually happened:* Web Mercator area inflates by $(1 / \cos(\text{lat}))^2$, exaggerating high-latitude features by over $400\%$.  
   *What I changed:* Implemented detection logic that intercepts cylindrical Mercator projections and reroutes them to UTM or LAEA.

4. **Transient Test Database Connections:**
   *What I assumed:* An in-memory SQLite database (`sqlite:///:memory:`) could be shared across async threadpool workers.  
   *What actually happened:* SQLite creates a separate isolated database per connection in memory, causing workers to miss newly created file rows.  
   *What I changed:* Configured test fixtures to use a temporary disk-backed SQLite file with WAL journal mode.

5. **ESRI Shapefile Component Coupling:**
   *What I assumed:* Shapefiles could be parsed from standalone `.shp` files.  
   *What actually happened:* GDAL and OGR require `.shx` and `.dbf` companions. Missing either causes low-level OGR read failures.  
   *What I changed:* Implemented archive discovery that validates sibling components before invoking GDAL.

---

## 12. Future Scope

### Near Term (Next Sprint)
- **Task Worker Queue:** Replace in-process `BackgroundTasks` with Celery or Arq backed by Redis for multi-gigabyte files.
- **Additional Vector Formats:** Expand `ReaderFactory` to support GeoPackage (`.gpkg`), GeoJSON, and DXF files.
- **Deduplication:** Hash-based deduplication using stored `sha256` digests to avoid re-processing identical uploads.

### Mid Term (Next Quarter)
- **PostGIS Storage Option:** Provide native `GEOMETRY` column persistence with GiST spatial indexing for geospatial queries.
- **Progress Streaming:** Server-Sent Events (SSE) or WebSockets to report real-time ingestion progress.
- **Interactive Map Preview:** Lightweight Leaflet/MapLibre web UI to visualize uploaded layers and measurements in the browser.

### Long Term (Enterprise Roadmap)
- **Vector Tiling:** Generate on-the-fly Mapbox Vector Tiles (MVT) for large datasets.
- **Observability:** Prometheus metrics (`/metrics`) and OpenTelemetry distributed tracing.
- **Kubernetes Helm Chart:** Production deployment chart with Horizontal Pod Autoscaling (HPA) and ingress configurations.

---

## 13. Project Info

- **Repository:** [https://github.com/adisri19/geomeasure](https://github.com/adisri19/geomeasure)
- **License:** MIT License. See [LICENSE](LICENSE) for details.
- **Author:** Aditya Srivastava ([@adisri19](https://github.com/adisri19))
- **Acknowledgements:** Built with [FastAPI](https://fastapi.tiangolo.com), [pyogrio](https://pyogrio.readthedocs.io), [Shapely](https://shapely.readthedocs.io), [PyProj](https://pyproj4.github.io/pyproj), and [SQLAlchemy](https://www.sqlalchemy.org).
