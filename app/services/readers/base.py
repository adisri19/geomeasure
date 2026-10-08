"""Base abstract reader protocol and normalized data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import shapely


@dataclass
class RawFeature:
    """Normalized feature record yielded by file readers."""

    feature_index: int
    source_feature_id: str | None
    layer_name: str
    geometry: shapely.Geometry | None
    properties: dict[str, Any]
    crs: str
    geometry_type: str


@dataclass
class FileMetadata:
    """Summary metadata extracted from a geospatial file."""

    crs: str
    crs_wkt: str | None = None
    crs_assumed: bool = False
    layer_names: list[str] = field(default_factory=list)
    feature_count: int = 0
    warnings: list[str] = field(default_factory=list)


class BaseReader(ABC):
    """Abstract base reader providing common interface for geospatial file ingestion."""

    @abstractmethod
    def read(self, path: Path) -> tuple[FileMetadata, list[RawFeature]]:
        """Read geospatial file or unpacked directory and return normalized metadata and features.

        Args:
            path: Path to the target file or extraction directory.

        Returns:
            Tuple of (FileMetadata, list of RawFeature).
        """
        pass
