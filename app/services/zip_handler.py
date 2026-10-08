"""Secure ZIP archive extractor with Zip-Slip, Zip-Bomb, and Shapefile discovery defenses."""

import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import (
    InvalidArchiveException,
    ShapefileMissingComponentsException,
    ShapefileNotFoundException,
    UnsafeArchiveException,
)
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class DiscoveredShapefile:
    """Represents a validated shapefile and its companion files on disk."""

    name: str
    shp_path: Path
    shx_path: Path
    dbf_path: Path
    prj_path: Path | None
    cpg_path: Path | None


class SafeZipExtractor:
    """Safe extractor for zip archives enforcing strict security constraints."""

    @classmethod
    def extract_and_find_shapefiles(
        cls, zip_path: Path, extract_dir: Path
    ) -> list[DiscoveredShapefile]:
        """Safely unpack an uploaded zip archive and discover valid shapefile bundles.

        Args:
            zip_path: Path to the validated zip file on disk.
            extract_dir: Temporary directory destination for unpacked files.

        Returns:
            List of DiscoveredShapefile instances.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # 1. Zip Bomb Defense: Entry count check
                entries = zf.infolist()
                if len(entries) > settings.MAX_ZIP_ENTRIES:
                    raise UnsafeArchiveException(
                        message=f"Archive contains {len(entries)} entries, exceeding safety limit of {settings.MAX_ZIP_ENTRIES}"
                    )

                # 2. Check for password encryption
                for member in entries:
                    if member.flag_bits & 0x1:
                        raise InvalidArchiveException(
                            "Password-protected zip archives are not supported"
                        )

                # 3. Zip Bomb & Zip Slip Defense during scan
                total_uncompressed = 0
                dest_dir_resolved = str(extract_dir.resolve())

                for member in entries:
                    # Ignore directory entries
                    if member.is_dir():
                        continue

                    # 3.1 Zip-Slip / Path Traversal Defense FIRST
                    clean_name = member.filename.replace("\\", "/")
                    if ".." in clean_name or clean_name.startswith("/"):
                        raise UnsafeArchiveException(
                            f"Path traversal detected in archive entry: {member.filename}"
                        )

                    target_path = Path(dest_dir_resolved) / clean_name
                    try:
                        target_resolved = str(target_path.resolve())
                    except Exception as e:
                        raise UnsafeArchiveException(
                            "Invalid or suspicious path detected in archive entry"
                        ) from e

                    if not target_resolved.startswith(dest_dir_resolved):
                        raise UnsafeArchiveException(
                            f"Path traversal detected in archive entry: {member.filename}"
                        )

                    # 3.2 Filter macOS junk, DS_Store, hidden files AFTER security validation
                    parts = clean_name.split("/")
                    if any(p.startswith(".") or p == "__MACOSX" for p in parts if p):
                        continue

                    # Symlink / special file defense
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode) or stat.S_ISFIFO(mode):
                        logger.warning(
                            "Ignoring symlink/special archive entry: %s", member.filename
                        )
                        continue

                    # Zip-Bomb size and ratio checks
                    total_uncompressed += member.file_size
                    if total_uncompressed > settings.max_uncompressed_bytes:
                        raise UnsafeArchiveException(
                            f"Uncompressed archive size exceeds limit of {settings.MAX_UNCOMPRESSED_MB} MB"
                        )

                    if member.compress_size > 0:
                        ratio = member.file_size / member.compress_size
                        if (
                            ratio > settings.MAX_COMPRESSION_RATIO
                            and member.file_size > 1024 * 1024
                        ):
                            raise UnsafeArchiveException(
                                f"Suspicious compression ratio ({ratio:.1f}:1) detected for {member.filename}"
                            )

                    # Extract file safely
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as source, target_path.open("wb") as target:
                        # Stream copy in chunks to protect memory
                        while True:
                            chunk = source.read(64 * 1024)
                            if not chunk:
                                break
                            target.write(chunk)

        except (zipfile.BadZipFile, zipfile.LargeZipFile) as e:
            raise InvalidArchiveException(f"Corrupt or invalid zip archive: {e}") from e
        except RuntimeError as e:
            # zipfile raises RuntimeError for encrypted or corrupted entries
            raise InvalidArchiveException(f"Failed to extract archive: {e}") from e

        # 4. Shapefile Component Discovery
        return cls._discover_shapefiles(extract_dir)

    @classmethod
    def _discover_shapefiles(cls, base_dir: Path) -> list[DiscoveredShapefile]:
        """Scan directory tree for .shp files and verify companion components."""
        # Find all .shp files case-insensitively
        shp_files: list[Path] = []
        for root, _, files in os.walk(base_dir):
            for f in files:
                if f.lower().endswith(".shp"):
                    shp_files.append(Path(root) / f)

        if not shp_files:
            raise ShapefileNotFoundException(
                "No .shp file found inside the archive. Ensure the zip contains the shapefile components."
            )

        discovered: list[DiscoveredShapefile] = []
        for shp in shp_files:
            folder = shp.parent
            base_stem = shp.stem.lower()

            # Map existing files in same folder by lowercase extension
            folder_files = {f.name.lower(): f for f in folder.iterdir() if f.is_file()}

            shx_key = f"{base_stem}.shx"
            dbf_key = f"{base_stem}.dbf"
            prj_key = f"{base_stem}.prj"
            cpg_key = f"{base_stem}.cpg"

            missing = []
            if shx_key not in folder_files:
                missing.append(f"{shp.stem}.shx")
            if dbf_key not in folder_files:
                missing.append(f"{shp.stem}.dbf")

            if missing:
                raise ShapefileMissingComponentsException(
                    message=f"Shapefile '{shp.name}' is missing required companion file(s): {', '.join(missing)}",
                    details={"missing_components": missing, "shapefile": shp.name},
                )

            discovered.append(
                DiscoveredShapefile(
                    name=shp.stem,
                    shp_path=shp,
                    shx_path=folder_files[shx_key],
                    dbf_path=folder_files[dbf_key],
                    prj_path=folder_files.get(prj_key),
                    cpg_path=folder_files.get(cpg_key),
                )
            )

        return discovered
