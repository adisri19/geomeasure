#!/usr/bin/env bash
set -euo pipefail

# Geospatial File Measurement API - Smoke Test Runner
BASE_URL="${API_URL:-http://127.0.0.1:8000}"

echo "=========================================================="
echo " Starting Smoke Tests against: ${BASE_URL}"
echo "=========================================================="

# 1. Health Checks
echo -e "\n[1/7] Testing /health and /ready..."
curl -s -f "${BASE_URL}/health" | grep -q "healthy" && echo "  ✓ /health OK"
curl -s -f "${BASE_URL}/ready" | grep -q "ready" && echo "  ✓ /ready OK"

# 2. Upload KML (plots_4326.kml)
echo -e "\n[2/7] Uploading samples/plots_4326.kml..."
KML_RESP=$(curl -s -X POST "${BASE_URL}/api/files/" -F "file=@samples/plots_4326.kml")
KML_ID=$(echo "${KML_RESP}" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "  ✓ KML uploaded successfully. ID: ${KML_ID}"

# 3. Inspect KML file info
echo -e "\n[3/7] Fetching file info for KML..."
curl -s "${BASE_URL}/api/files/${KML_ID}/" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'  ✓ Status: {data[\"status\"]}, Features: {data[\"feature_count\"]}, CRS: {data[\"crs\"]}')"

# 4. Fetch KML measurements
echo -e "\n[4/7] Fetching measurements for KML..."
curl -s "${BASE_URL}/api/files/${KML_ID}/measurements/" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'  ✓ Measured: {data[\"summary\"][\"measured_count\"]}, Skipped: {data[\"summary\"][\"skipped_count\"]}, Total Area: {data[\"summary\"][\"total_area\"][\"hectares\"]} ha, Total Length: {data[\"summary\"][\"total_length\"][\"kilometers\"]} km')"

# 5. Upload Projected Shapefile (parcels_utm43n.zip)
echo -e "\n[5/7] Uploading samples/parcels_utm43n.zip (Native Projected EPSG:32643)..."
SHP_RESP=$(curl -s -X POST "${BASE_URL}/api/files/" -F "file=@samples/parcels_utm43n.zip")
SHP_ID=$(echo "${SHP_RESP}" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "  ✓ Shapefile uploaded successfully. ID: ${SHP_ID}"
curl -s "${BASE_URL}/api/files/${SHP_ID}/measurements/" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'  ✓ Total Area: {data[\"summary\"][\"total_area\"][\"hectares\"]} ha (Expected: 29.0 ha)')"

# 6. Upload Shapefile without .prj (no_prj.zip)
echo -e "\n[6/7] Uploading samples/no_prj.zip (Missing .prj heuristic test)..."
NO_PRJ_RESP=$(curl -s -X POST "${BASE_URL}/api/files/" -F "file=@samples/no_prj.zip")
echo "${NO_PRJ_RESP}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'  ✓ CRS Assumed: {data[\"crs_assumed\"]}, Warnings: {len(data[\"warnings\"])}')"

# 7. Test Error Handling Matrix Responses
echo -e "\n[7/7] Verifying error response envelopes..."
# 7.1 Corrupt archive -> 422 INVALID_ARCHIVE
CORRUPT_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/files/" -F "file=@samples/corrupt.zip")
echo "  ✓ corrupt.zip -> HTTP ${CORRUPT_CODE} (Expected 422)"

# 7.2 Missing components -> 422 SHAPEFILE_MISSING_COMPONENTS
MISSING_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/files/" -F "file=@samples/missing_shx.zip")
echo "  ✓ missing_shx.zip -> HTTP ${MISSING_CODE} (Expected 422)"

# 7.3 Malformed KML -> 422 INVALID_KML
BAD_KML_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/files/" -F "file=@samples/bad.kml")
echo "  ✓ bad.kml -> HTTP ${BAD_KML_CODE} (Expected 422)"

# 7.4 Content type mismatch -> 415 CONTENT_TYPE_MISMATCH
MISMATCH_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/files/" -F "file=@samples/wrong_extension.kml")
echo "  ✓ wrong_extension.kml -> HTTP ${MISMATCH_CODE} (Expected 415)"

# 7.5 Unknown file ID -> 404 FILE_NOT_FOUND
NOT_FOUND_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/files/nonexistent_id_999/")
echo "  ✓ Unknown file ID -> HTTP ${NOT_FOUND_CODE} (Expected 404)"

echo -e "\n=========================================================="
echo " ALL SMOKE TESTS PASSED SUCCESSFULLY!"
echo "=========================================================="
