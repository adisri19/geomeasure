# Application Architecture & System Design

## 1. System Overview & Clean Layered Architecture

The **Geospatial File Measurement API** is engineered following strict Clean Architecture and Domain-Driven Design principles. High-level routing layers are decoupled from business services, which in turn are isolated from persistence and raw I/O boundaries.

```mermaid
graph TD
    subgraph Presentation ["Presentation Layer (FastAPI)"]
        API["API Routers (/api/files, /health, /ready)"]
        Middleware["Middlewares (RequestId, GZip, CORS)"]
        Schemas["Pydantic Schemas & DTOs"]
    end

    subgraph Service ["Domain & Service Layer"]
        UploadSvc["Upload Orchestrator (upload_service.py)"]
        ValidationSvc["File & Magic Sniffer (file_validation.py)"]
        ZipExtractor["Safe Zip Extractor (zip_handler.py)"]
        ReaderFactory["Reader Factory & Parsers (readers/)"]
        CRSSvc["CRS Engine & UTM Selector (crs_service.py)"]
        GeomSvc["Topology & Repair (geometry_service.py)"]
        MeasSvc["Measurement Engine (measurement_service.py)"]
    end

    subgraph Persistence ["Persistence Layer"]
        FileRepo["File Repository (file_repository.py)"]
        Models["SQLAlchemy 2.0 ORM Models"]
        DB[(Database: SQLite / PostgreSQL)]
    end

    API --> UploadSvc
    UploadSvc --> ValidationSvc
    UploadSvc --> ZipExtractor
    UploadSvc --> ReaderFactory
    UploadSvc --> GeomSvc
    UploadSvc --> CRSSvc
    UploadSvc --> MeasSvc
    UploadSvc --> FileRepo
    FileRepo --> Models
    Models --> DB
```

---

## 2. End-to-End File Processing Flow

The processing pipeline is executed synchronously by default (yielding an immediate `201 Created` with full results) or asynchronously via `?async=true` (yielding `202 Accepted` and background execution).

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

---

## 3. Entity-Relationship Data Model

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
