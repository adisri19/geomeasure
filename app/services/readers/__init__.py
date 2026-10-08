"""Geospatial file reader components and protocols."""

from app.services.readers.base import BaseReader, FileMetadata, RawFeature
from app.services.readers.factory import ReaderFactory
from app.services.readers.kml_reader import KmlReader
from app.services.readers.shapefile_reader import ShapefileReader

__all__ = [
    "BaseReader",
    "FileMetadata",
    "RawFeature",
    "ReaderFactory",
    "ShapefileReader",
    "KmlReader",
]
