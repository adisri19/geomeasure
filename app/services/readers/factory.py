"""Reader factory implementing the Strategy/Factory pattern for format readers."""

from app.core.constants import FileType
from app.services.readers.base import BaseReader
from app.services.readers.kml_reader import KmlReader
from app.services.readers.shapefile_reader import ShapefileReader


class ReaderFactory:
    """Factory selecting the appropriate geospatial reader based on file type."""

    _readers: dict[FileType, type[BaseReader]] = {
        FileType.SHAPEFILE: ShapefileReader,
        FileType.KML: KmlReader,
    }

    @classmethod
    def get_reader(cls, file_type: FileType) -> BaseReader:
        """Instantiate and return reader strategy for the requested file type."""
        reader_cls = cls._readers.get(file_type)
        if not reader_cls:
            raise ValueError(f"No reader strategy registered for file type: {file_type}")
        return reader_cls()
