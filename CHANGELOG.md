# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-09

### Added
- Core backend service using FastAPI, pyogrio (GDAL C-bindings), Shapely 2.0, and PyProj.
- Multipart ingestion endpoints `POST /api/files/` supporting `.zip` (ESRI Shapefiles) and `.kml` documents.
- Automatic trailing-slash dual route support (`/api/files/` and `/api/files`).
- Dynamic projected CRS selection strategy:
  - Automatic UTM zone calculation by centroid longitude with Norway and Svalbard exceptions.
  - Universal Polar Stereographic (UPS) fallback for polar regions (|lat| >= 84°).
  - Custom Lambert Azimuthal Equal-Area (LAEA) projection for continental spans > 6°.
  - Native projected CRS passthrough with linear and area unit normalization (international and US survey feet).
  - Conformal distortion detection rerouting Web Mercator (`EPSG:3857`).
- Dual-engine ellipsoidal geodesic cross-validation via `pyproj.Geod(ellps="WGS84")`.
- Archive security defenses: Zip-Slip path traversal prevention, Zip-Bomb limits (ratios, uncompressed size, entries), and password detection.
- XML security: hardened `defusedxml` parser blocking XXE and billion-laughs attacks.
- Robust missing `.prj` handling: bounding box degree heuristic for `EPSG:4326` assumption and `422 CRS_UNDEFINED` rejection.
- Failure isolation per feature: single bad or degenerate geometries do not abort file processing.
- Comprehensive REST endpoints: `GET /api/files/{id}/`, `GET /api/files/{id}/measurements/`, `GET /api/files/`, `GET /api/files/{id}/features/{index}/`, `DELETE /api/files/{id}/`.
- System probes: `/health` (liveness) and `/ready` (readiness with database and GDAL driver checks).
- Multi-stage non-root Dockerfile and `docker-compose.yml`.
- Developer Makefile and automated curl-based smoke test suite (`scripts/smoke_test.sh`).
- Full unit, integration, and property test suite with >= 90% code coverage.
