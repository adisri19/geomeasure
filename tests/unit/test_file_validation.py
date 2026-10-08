"""Unit tests for file extension validation, content sniffing, and streaming limits."""

import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.core.constants import FileType
from app.core.errors import (
    ContentTypeMismatchException,
    EmptyFileException,
    FileTooLargeException,
    UnsupportedFileTypeException,
)
from app.services.file_validation import (
    detect_file_type_by_extension,
    sniff_content_type,
    stream_validate_and_save,
)


def test_detect_file_type_by_extension() -> None:
    assert detect_file_type_by_extension("survey.zip") == FileType.SHAPEFILE
    assert detect_file_type_by_extension("SURVEY.ZIP") == FileType.SHAPEFILE
    assert detect_file_type_by_extension("boundaries.kml") == FileType.KML
    assert detect_file_type_by_extension("BOUNDARIES.KML") == FileType.KML

    with pytest.raises(UnsupportedFileTypeException, match="KMZ files are not directly accepted"):
        detect_file_type_by_extension("map.kmz")

    with pytest.raises(UnsupportedFileTypeException, match="Unsupported file extension"):
        detect_file_type_by_extension("data.geojson")


def test_sniff_content_type_mismatch() -> None:
    # PNG disguised as KML
    png_bytes = io.BytesIO(b"\x89PNG\r\n\x1a\nfake_image_data")
    with pytest.raises(ContentTypeMismatchException, match="not a valid KML"):
        sniff_content_type(png_bytes, FileType.KML)

    # Text disguised as ZIP
    txt_bytes = io.BytesIO(b"Just plain text without zip header")
    with pytest.raises(ContentTypeMismatchException, match="not a valid ZIP archive"):
        sniff_content_type(txt_bytes, FileType.SHAPEFILE)


def test_sniff_empty_file() -> None:
    empty_stream = io.BytesIO(b"")
    with pytest.raises(EmptyFileException):
        sniff_content_type(empty_stream, FileType.SHAPEFILE)


@pytest.mark.asyncio
async def test_stream_validate_exceeding_max_bytes(tmp_path: Path) -> None:
    # Set limit to 100 bytes and stream 500 bytes
    large_payload = b"PK\x03\x04" + (b"A" * 500)
    upload = UploadFile(
        file=io.BytesIO(large_payload),
        filename="overflow.zip",
    )
    dest = tmp_path / "saved.zip"

    with pytest.raises(FileTooLargeException, match="exceeds maximum allowed upload size"):
        await stream_validate_and_save(upload, dest, max_bytes=100)

    # Confirm cleaned up
    assert not dest.exists()
