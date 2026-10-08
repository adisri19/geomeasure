"""File validation service for upload security, content sniffing, and streaming size limits."""

import hashlib
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.constants import FileType
from app.core.errors import (
    ContentTypeMismatchException,
    EmptyFileException,
    FileTooLargeException,
    UnsupportedFileTypeException,
)
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

ZIP_MAGIC = b"PK\x03\x04"
ZIP_SPANNED_MAGIC = b"PK\x07\x08"
XML_PROLOG = b"<?xml"
KML_TAG = b"<kml"


def detect_file_type_by_extension(filename: str) -> FileType:
    """Validate file extension against allowlist and return normalized FileType."""
    lower_name = filename.lower()
    if lower_name.endswith(".zip"):
        return FileType.SHAPEFILE
    if lower_name.endswith(".kml"):
        return FileType.KML
    if lower_name.endswith(".kmz"):
        # KMZ is a zipped KML; per design, we direct users to .kml or .zip shapefile
        raise UnsupportedFileTypeException(
            message="KMZ files are not directly accepted. Please extract and upload as .kml or provide a Shapefile .zip"
        )
    raise UnsupportedFileTypeException(
        message=f"Unsupported file extension in '{filename}'. Accepted formats are .zip (Shapefile) and .kml"
    )


def sniff_content_type(file_obj: BinaryIO, expected_type: FileType) -> None:
    """Sniff leading magic bytes to ensure file contents match claimed format."""
    current_pos = file_obj.tell()
    file_obj.seek(0)
    header = file_obj.read(1024)
    file_obj.seek(current_pos)

    if not header:
        raise EmptyFileException()

    if expected_type == FileType.SHAPEFILE:
        if not (header.startswith(ZIP_MAGIC) or header.startswith(ZIP_SPANNED_MAGIC)):
            raise ContentTypeMismatchException(
                message="File extension is .zip but file header is not a valid ZIP archive"
            )

    elif expected_type == FileType.KML:
        # Check if header contains XML prolog or <kml tag (case-insensitive)
        lower_header = header.lower()
        has_kml = KML_TAG in lower_header or (XML_PROLOG in lower_header and b"kml" in lower_header)
        if not has_kml:
            raise ContentTypeMismatchException(
                message="File extension is .kml but content is not a valid KML/XML document"
            )


async def stream_validate_and_save(
    upload_file: UploadFile,
    dest_path: Path,
    max_bytes: int | None = None,
) -> tuple[int, str, FileType]:
    """Stream file upload to disk while enforcing max size and computing SHA256.

    Returns:
        tuple of (total_bytes, sha256_hex, file_type)
    """
    if not upload_file.filename:
        raise UnsupportedFileTypeException("No filename provided with upload")

    file_type = detect_file_type_by_extension(upload_file.filename)
    limit = max_bytes or settings.max_upload_bytes

    sha256 = hashlib.sha256()
    total_bytes = 0
    first_chunk = True

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with dest_path.open("wb") as out_file:
        while True:
            chunk = await upload_file.read(64 * 1024)  # 64 KB chunks
            if not chunk:
                break

            total_bytes += len(chunk)
            if total_bytes > limit:
                # Clean up partially written file
                out_file.close()
                if dest_path.exists():
                    dest_path.unlink()
                raise FileTooLargeException(
                    message=f"File exceeds maximum allowed upload size of {limit // (1024 * 1024)} MB"
                )

            if first_chunk:
                first_chunk = False
                # Fast in-memory header sniff on first chunk
                if file_type == FileType.SHAPEFILE and not (
                    chunk.startswith(ZIP_MAGIC) or chunk.startswith(ZIP_SPANNED_MAGIC)
                ):
                    out_file.close()
                    if dest_path.exists():
                        dest_path.unlink()
                    raise ContentTypeMismatchException(
                        message="File extension is .zip but contents do not match ZIP signature"
                    )
                if file_type == FileType.KML:
                    lower_chunk = chunk.lower()
                    if not (
                        KML_TAG in lower_chunk
                        or (XML_PROLOG in lower_chunk and b"kml" in lower_chunk)
                    ):
                        out_file.close()
                        if dest_path.exists():
                            dest_path.unlink()
                        raise ContentTypeMismatchException(
                            message="File extension is .kml but contents do not match KML/XML signature"
                        )

            sha256.update(chunk)
            out_file.write(chunk)

    if total_bytes == 0:
        if dest_path.exists():
            dest_path.unlink()
        raise EmptyFileException("Uploaded file is empty (0 bytes)")

    return total_bytes, sha256.hexdigest(), file_type
