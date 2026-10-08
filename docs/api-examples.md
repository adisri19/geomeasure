# API Reference & End-to-End Examples

Comprehensive reference and worked request/response payloads for every endpoint exposed by the **Geospatial File Measurement API**.

---

## Base URL & Routing Conventions
- **Base Prefix:** `/api`
- **Trailing Slashes:** Both `/api/files/` and `/api/files` routes are registered natively to avoid dropping multipart bodies on HTTP redirects.
- **Interactive Documentation:**
  - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
  - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
  - OpenAPI Specification: [docs/openapi.json](openapi.json)

---

## 1. POST /api/files/ — Upload and Process File

Accepts a multipart form-data upload containing either a Shapefile archive (`.zip`) or a KML document (`.kml`).

### Parameters
| Name | Type | In | Required | Default | Description |
|:---|:---|:---|:---:|:---:|:---|
| `file` | `UploadFile` | `formData` | Yes | — | Geospatial archive (`.zip` Shapefile) or `.kml` XML document |
| `async` | `boolean` | `query` | No | `false` | When `true`, returns `202 Accepted` immediately and processes features in the background |

### Example 1: Synchronous KML Upload
```bash
curl -i -X POST http://localhost:8000/api/files/ \
  -F "file=@samples/plots_4326.kml"
```

**Response (`201 Created`):**
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

### Example 2: Asynchronous Background Ingestion
```bash
curl -i -X POST "http://localhost:8000/api/files/?async=true" \
  -F "file=@samples/parcels_utm43n.zip"
```

**Response (`202 Accepted`):**
```http
HTTP/1.1 202 Accepted
Location: /api/files/48ae7012bc09/
Content-Type: application/json
```
```json
{
  "id": "48ae7012bc09",
  "filename": "parcels_utm43n.zip",
  "feature_count": 0,
  "crs": "PENDING",
  "status": "PENDING",
  "file_type": "SHAPEFILE",
  "size_bytes": 1058,
  "sha256": "977f2c400c3ea22582cc34f0ace56d20011699611d49f7c3dbc4e7a469851b99",
  "geometry_type_counts": {},
  "crs_assumed": false,
  "warnings": [],
  "error": null,
  "created_at": "2026-10-08T22:48:05",
  "processed_at": null,
  "processing_ms": null,
  "links": {
    "self": "/api/files/48ae7012bc09/",
    "measurements": "/api/files/48ae7012bc09/measurements/"
  }
}
```

---

## 2. GET /api/files/{id}/ — File Metadata Inspection

Returns file metadata and geometry breakdown. Verbatim conforms to the hiring brief requirements (`id, filename, feature_count, crs, status`).

### Parameters
| Name | Type | In | Required | Description |
|:---|:---|:---|:---:|:---|
| `file_id` | `string` | `path` | Yes | 12-character unique file identifier |

```bash
curl -s http://localhost:8000/api/files/26875053bf12/ | jq .
```

**Response (`200 OK`):**
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

---

## 3. GET /api/files/{id}/measurements/ — Calculated Feature Measurements

Returns computed area/length measurements, aggregates, and pagination metadata.

### Parameters
| Name | Type | In | Required | Default | Description |
|:---|:---|:---|:---:|:---:|:---|
| `file_id` | `string` | `path` | Yes | — | Unique file identifier |
| `limit` | `integer` | `query` | No | `100` | Number of features to return (min: 1, max: 1000) |
| `offset` | `integer` | `query` | No | `0` | Pagination offset |
| `geometry_type` | `string` | `query` | No | `null` | Optional geometry filter (`Polygon`, `LineString`, `Point`) |
| `include_geometry` | `boolean` | `query` | No | `true` | Include GeoJSON geometry objects in response |
| `precision` | `integer` | `query` | No | `4` | Number of decimal places for numeric outputs |

```bash
curl -s "http://localhost:8000/api/files/26875053bf12/measurements/?limit=1&precision=2" | jq .
```

**Response (`200 OK`):**
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
    "limit": 1,
    "offset": 0,
    "total": 5,
    "next": "/api/files/26875053bf12/measurements/?limit=1&offset=1",
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

---

## 4. GET /api/files/ — List Uploaded Files

Returns a paginated list of uploaded files, optionally filtered by processing status.

```bash
curl -s "http://localhost:8000/api/files/?limit=10&status=COMPLETED" | jq .
```

**Response (`200 OK`):**
```json
{
  "items": [
    {
      "id": "26875053bf12",
      "filename": "plots_4326.kml",
      "feature_count": 5,
      "crs": "EPSG:4326",
      "status": "COMPLETED",
      "file_type": "KML",
      "size_bytes": 3014,
      "sha256": "69dec06e63c3bec56a3387460e7d906df177d406c9dba046cf933ff6955a5ecd",
      "geometry_type_counts": {"Polygon": 2, "LineString": 1, "Point": 1, "None": 1},
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
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

---

## 5. GET /api/files/{id}/features/{feature_index}/ — Single Feature Lookup

```bash
curl -s http://localhost:8000/api/files/26875053bf12/features/0/ | jq .
```

**Response (`200 OK`):**
```json
{
  "feature_index": 0,
  "id": "plot_nashik_01",
  "layer_name": "Parcels",
  "geometry_type": "Polygon",
  "crs": "EPSG:4326",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[73.78, 19.99], [73.8, 19.99], [73.8, 20.01], [73.78, 20.01], [73.78, 19.99]]]
  },
  "properties": {
    "name": "Nashik Vineyard Estate"
  },
  "measurement": {
    "type": "area",
    "status": "OK",
    "area_m2": 3474060.6338,
    "area_hectares": 347.4061,
    "area_acres": 858.4591,
    "area_sq_km": 3.4741,
    "perimeter_m": 12918.4728,
    "length_m": null,
    "length_km": null,
    "length_miles": null,
    "geodesic_area_m2": 5792440.6042,
    "geodesic_length_m": null,
    "method": "UTM Zone 43N (EPSG:32643)",
    "projected_crs": "EPSG:32643",
    "note": null
  }
}
```

---

## 6. DELETE /api/files/{id}/ — Delete File

Deletes the file record and cascades deletion of all associated feature records.

```bash
curl -i -X DELETE http://localhost:8000/api/files/26875053bf12/
```

**Response (`204 No Content`):**
```http
HTTP/1.1 204 No Content
```

---

## 7. System Health & Readiness Probes

### GET /health (Liveness)
```bash
curl -s http://localhost:8000/health
```
```json
{"status": "healthy"}
```

### GET /ready (Readiness)
Verifies database connection and GDAL drivers (`ESRI Shapefile`, `KML`/`LIBKML`).
```bash
curl -s http://localhost:8000/ready
```
```json
{
  "status": "ready",
  "checks": {
    "database": true,
    "gdal_drivers": true
  },
  "details": {}
}
```
If checks fail, returns `503 Service Unavailable` with details.
