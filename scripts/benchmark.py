"""Benchmark script to measure ingestion and measurement throughput with 10,000 synthetic features."""

import os
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np
import pyogrio.raw
import pyproj
import shapely
from shapely.geometry import Polygon

from app.core.constants import FileType
from app.db.session import SessionLocal, init_db
from app.services.upload_service import _execute_processing_pipeline


def generate_synthetic_shapefile(num_features: int, dest_zip: Path) -> None:
    """Generate a synthetic shapefile with the given number of polygon features."""
    with tempfile.TemporaryDirectory() as td:
        shp_path = Path(td) / "benchmark_polygons.shp"

        # Generate a grid of small parcels in Maharashtra (EPSG:4326)
        base_lon = 73.5
        base_lat = 19.5
        step = 0.005

        cols = 100
        polygons = []
        names = []
        ids = []

        for i in range(num_features):
            row = i // cols
            col = i % cols
            x = base_lon + col * step
            y = base_lat + row * step
            p = Polygon([(x, y), (x + 0.003, y), (x + 0.003, y + 0.003), (x, y + 0.003), (x, y)])
            polygons.append(shapely.to_wkb(p))
            names.append(f"Parcel {i}")
            ids.append(i)

        geoms_arr = np.array(polygons, dtype=object)
        field_data = [
            np.array(names, dtype=object),
            np.array(ids, dtype=np.int32),
        ]
        fields = ["name", "parcel_id"]

        crs_wkt = pyproj.CRS.from_epsg(4326).to_wkt()
        pyogrio.raw.write(
            str(shp_path),
            geometry=geoms_arr,
            field_data=field_data,
            fields=fields,
            geometry_type="Polygon",
            crs=crs_wkt,
        )

        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in Path(td).iterdir():
                zf.write(f, f.name)


def run_benchmark(feature_count: int = 10000) -> None:
    """Run ingestion, reprojection, and measurement benchmark."""
    init_db()
    with tempfile.TemporaryDirectory() as work_dir:
        zip_path = Path(work_dir) / "benchmark.zip"

        print(f"Generating synthetic shapefile with {feature_count:,} features...")
        gen_start = time.perf_counter()
        generate_synthetic_shapefile(feature_count, zip_path)
        gen_time = time.perf_counter() - gen_start
        file_size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"Generated {feature_count:,} features in {gen_time:.2f}s ({file_size_mb:.2f} MB)")

        print("Executing measurement processing pipeline...")
        proc_start = time.perf_counter()
        # Execute pipeline
        file_id = f"bench_{int(time.time())}"
        # Create dummy file entry in DB
        from app.db.models import UploadedFile
        from app.repositories.file_repository import FileRepository

        session = SessionLocal()
        dummy_file = UploadedFile(
            id=file_id,
            filename="benchmark.zip",
            file_type=FileType.SHAPEFILE.value,
            size_bytes=zip_path.stat().st_size,
            sha256="benchmark_hash",
            feature_count=0,
            crs="PENDING",
            status="PENDING",
            warnings=[],
            layer_names=[],
        )
        FileRepository.create_file(session, dummy_file)
        session.close()

        _execute_processing_pipeline(
            file_id=file_id,
            temp_file_path=zip_path,
            file_type=FileType.SHAPEFILE,
        )
        proc_time = time.perf_counter() - proc_start

        # Fetch results
        session = SessionLocal()
        summary = FileRepository.get_file_summary(session, file_id)
        session.close()

        features_per_sec = feature_count / proc_time
        print("\n=== BENCHMARK RESULTS ===")
        print(f"Feature count:        {feature_count:,}")
        print(f"Total time:           {proc_time:.2f} seconds")
        print(f"Throughput:           {features_per_sec:.1f} features / sec")
        print(f"Total measured area:  {summary['total_area_m2'] / 1e6:.2f} km²")
        print(f"Measured count:       {summary['measured_count']:,}")
        print(f"Skipped count:        {summary['skipped_count']}")
        print("========================\n")


if __name__ == "__main__":
    count = int(os.environ.get("BENCHMARK_COUNT", 10000))
    run_benchmark(count)
