"""Unit tests for safe zip extraction, path traversal defenses, zip-bomb checks, and discovery."""

import io
import tempfile
import zipfile
from pathlib import Path

import pytest

from app.core.errors import (
    InvalidArchiveException,
    ShapefileMissingComponentsException,
    ShapefileNotFoundException,
    UnsafeArchiveException,
)
from app.services.zip_handler import SafeZipExtractor


def test_zip_slip_traversal_rejected(tmp_path: Path) -> None:
    # Construct archive with a path traversal entry '../evil.shp'
    zip_file = tmp_path / "zipslip.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("../evil.shp", b"test")

    with (
        tempfile.TemporaryDirectory() as td,
        pytest.raises(UnsafeArchiveException, match="Path traversal"),
    ):
        SafeZipExtractor.extract_and_find_shapefiles(zip_file, Path(td))


def test_zip_bomb_excessive_entries_rejected(tmp_path: Path) -> None:
    # 260 entries exceeds MAX_ZIP_ENTRIES default (250)
    zip_file = tmp_path / "too_many_entries.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        for i in range(260):
            zf.writestr(f"file_{i}.txt", b"abc")

    with (
        tempfile.TemporaryDirectory() as td,
        pytest.raises(UnsafeArchiveException, match="exceeding safety limit"),
    ):
        SafeZipExtractor.extract_and_find_shapefiles(zip_file, Path(td))


def test_password_protected_zip_rejected(tmp_path: Path) -> None:
    # Construct zip with general purpose encryption flag set (bit 0)
    zip_file = tmp_path / "encrypted.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.shp", b"secret data")
    raw = bytearray(buf.getvalue())
    raw[6] = raw[6] | 0x01
    cd_idx = raw.find(b"PK\x01\x02")
    if cd_idx != -1:
        raw[cd_idx + 8] = raw[cd_idx + 8] | 0x01
    zip_file.write_bytes(bytes(raw))

    with (
        tempfile.TemporaryDirectory() as td,
        pytest.raises(InvalidArchiveException, match="Password-protected"),
    ):
        SafeZipExtractor.extract_and_find_shapefiles(zip_file, Path(td))


def test_missing_shapefile_components_rejected(tmp_path: Path) -> None:
    # Has .shp and .dbf but missing .shx
    zip_file = tmp_path / "missing_shx.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("roads.shp", b"shp_data")
        zf.writestr("roads.dbf", b"dbf_data")

    with (
        tempfile.TemporaryDirectory() as td,
        pytest.raises(ShapefileMissingComponentsException, match="missing required companion"),
    ):
        SafeZipExtractor.extract_and_find_shapefiles(zip_file, Path(td))


def test_no_shapefile_found_rejected(tmp_path: Path) -> None:
    zip_file = tmp_path / "no_shp.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("readme.txt", b"hello world")

    with (
        tempfile.TemporaryDirectory() as td,
        pytest.raises(ShapefileNotFoundException, match="No .shp file found"),
    ):
        SafeZipExtractor.extract_and_find_shapefiles(zip_file, Path(td))


def test_nested_folder_and_case_insensitive_discovery(tmp_path: Path) -> None:
    zip_file = tmp_path / "nested_case.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("subfolder/PARCELS.SHP", b"shp")
        zf.writestr("subfolder/PARCELS.SHX", b"shx")
        zf.writestr("subfolder/PARCELS.DBF", b"dbf")
        zf.writestr("subfolder/PARCELS.PRJ", b"prj")
        zf.writestr("__MACOSX/._PARCELS.SHP", b"junk")
        zf.writestr(".DS_Store", b"junk")

    with tempfile.TemporaryDirectory() as td:
        discovered = SafeZipExtractor.extract_and_find_shapefiles(zip_file, Path(td))
        assert len(discovered) == 1
        shp = discovered[0]
        assert shp.name.lower() == "parcels"
        assert shp.shp_path.exists()
        assert shp.shx_path.exists()
        assert shp.dbf_path.exists()
        assert shp.prj_path is not None and shp.prj_path.exists()
