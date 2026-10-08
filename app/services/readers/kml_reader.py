"""Hardened KML reader with defusedxml security, multi-folder extraction, and hole parsing."""

import xml.etree.ElementTree as standard_ET
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as defused_ET
import shapely
from defusedxml.common import DefusedXmlException
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

from app.core.errors import InvalidKmlException, NoFeaturesException
from app.core.logging import get_logger
from app.services.readers.base import BaseReader, FileMetadata, RawFeature

logger = get_logger(__name__)


def _parse_coordinates_text(text: str | None) -> list[tuple[float, float]]:
    """Parse KML coordinate tuple string 'lon,lat[,alt] ...' into 2D (lon, lat) tuples."""
    if not text:
        return []

    points: list[tuple[float, float]] = []
    # Split by whitespace / newlines
    tokens = text.strip().split()
    for token in tokens:
        parts = token.strip().split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                # Validate coordinates range
                if -360.0 <= lon <= 360.0 and -90.0 <= lat <= 90.0:
                    points.append((lon, lat))
            except ValueError:
                continue
    return points


class KmlReader(BaseReader):
    """Secure KML reader supporting Folders, ExtendedData, Polygon holes, and MultiGeometry."""

    def read(self, path: Path) -> tuple[FileMetadata, list[RawFeature]]:
        """Read KML file and extract all layers and features safely.

        Args:
            path: Path to the .kml file.

        Returns:
            Tuple of (FileMetadata, list of RawFeature).
        """
        try:
            content = path.read_bytes()
            if not content.strip():
                raise NoFeaturesException("KML file is empty")

            # Parse XML with defusedxml to block XXE & billion-laughs
            try:
                root = defused_ET.fromstring(content)
            except DefusedXmlException as e:
                raise InvalidKmlException(
                    message=f"KML rejected due to insecure XML entities (potential XXE attack): {e}"
                ) from e
            except standard_ET.ParseError as e:
                raise InvalidKmlException(f"Malformed or invalid XML in KML file: {e}") from e

        except (InvalidKmlException, NoFeaturesException):
            raise
        except Exception as e:
            raise InvalidKmlException(f"Unable to read KML document: {e}") from e

        # Extract namespace URI if present
        ns_uri = ""
        if root.tag.startswith("{"):
            ns_uri = root.tag.split("}")[0][1:]

        def _tag(name: str) -> str:
            return f"{{{ns_uri}}}{name}" if ns_uri else name

        all_raw_features: list[RawFeature] = []
        layer_names_set: set[str] = set()

        placemarks_with_layers = self._extract_placemarks_with_layers(root, _tag)

        for feature_index, (layer_name, placemark_elem) in enumerate(placemarks_with_layers):
            layer_names_set.add(layer_name)

            # Feature attributes
            name_elem = placemark_elem.find(_tag("name"))
            desc_elem = placemark_elem.find(_tag("description"))
            source_id = placemark_elem.get("id")

            properties: dict[str, Any] = {}
            if name_elem is not None and name_elem.text:
                properties["name"] = name_elem.text.strip()
            if desc_elem is not None and desc_elem.text:
                properties["description"] = desc_elem.text.strip()

            # Parse ExtendedData
            ext_elem = placemark_elem.find(_tag("ExtendedData"))
            if ext_elem is not None:
                for data_node in ext_elem.findall(_tag("Data")):
                    d_name = data_node.get("name")
                    val_node = data_node.find(_tag("value"))
                    if d_name and val_node is not None and val_node.text:
                        properties[d_name] = val_node.text.strip()
                for simple_data in ext_elem.iter(_tag("SimpleData")):
                    s_name = simple_data.get("name")
                    if s_name and simple_data.text:
                        properties[s_name] = simple_data.text.strip()

            # Parse Geometry
            geom = self._parse_kml_geometry(placemark_elem, _tag)
            geom_type = geom.geom_type if (geom is not None and not geom.is_empty) else "None"

            all_raw_features.append(
                RawFeature(
                    feature_index=feature_index,
                    source_feature_id=source_id,
                    layer_name=layer_name,
                    geometry=geom,
                    properties=properties,
                    crs="EPSG:4326",  # KML specification is always WGS84
                    geometry_type=geom_type,
                )
            )

        if not all_raw_features:
            raise NoFeaturesException("No Placemarks or geospatial features found in KML file")

        layer_names = sorted(layer_names_set) if layer_names_set else ["default"]

        file_metadata = FileMetadata(
            crs="EPSG:4326",
            crs_wkt=None,
            crs_assumed=False,
            layer_names=layer_names,
            feature_count=len(all_raw_features),
            warnings=[],
        )

        return file_metadata, all_raw_features

    def _extract_placemarks_with_layers(
        self,
        element: standard_ET.Element,
        tag_fn: Any,
        current_layer: str = "default",
    ) -> list[tuple[str, standard_ET.Element]]:
        """Traverse XML tree tracking enclosing Folder or Document names."""
        results: list[tuple[str, standard_ET.Element]] = []

        # If this node is a Folder or Document with a name, update current_layer
        tag_base = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        layer = current_layer
        if tag_base in ("Folder", "Document"):
            name_node = element.find(tag_fn("name"))
            if name_node is not None and name_node.text:
                layer = name_node.text.strip()

        for child in element:
            child_base = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_base == "Placemark":
                results.append((layer, child))
            elif child_base in ("Folder", "Document"):
                results.extend(self._extract_placemarks_with_layers(child, tag_fn, layer))
            else:
                # Recurse other containers
                results.extend(self._extract_placemarks_with_layers(child, tag_fn, layer))

        return results

    def _parse_kml_geometry(
        self, parent: standard_ET.Element, tag_fn: Any
    ) -> shapely.Geometry | None:
        """Parse geometry element under a Placemark or MultiGeometry."""
        raw_tag = parent.tag.split("}")[-1] if "}" in parent.tag else parent.tag

        # Check if parent is itself the geometry element
        if raw_tag == "Polygon":
            return self._parse_polygon(parent, tag_fn)
        if raw_tag in ("LineString", "LinearRing"):
            coords_node = parent.find(tag_fn("coordinates"))
            if coords_node is None:
                coords_node = parent.find("coordinates")
            pts = _parse_coordinates_text(coords_node.text if coords_node is not None else "")
            return LineString(pts) if len(pts) >= 2 else None
        if raw_tag == "Point":
            coords_node = parent.find(tag_fn("coordinates"))
            if coords_node is None:
                coords_node = parent.find("coordinates")
            pts = _parse_coordinates_text(coords_node.text if coords_node is not None else "")
            return Point(pts[0]) if pts else None
        if raw_tag == "MultiGeometry":
            parts = []
            for child in parent:
                child_geom = self._parse_kml_geometry(child, tag_fn)
                if child_geom is not None and not child_geom.is_empty:
                    parts.append(child_geom)
            if not parts:
                return None
            if all(isinstance(p, Polygon) for p in parts):
                return MultiPolygon(parts)
            if all(isinstance(p, LineString) for p in parts):
                return MultiLineString(parts)
            if all(isinstance(p, Point) for p in parts):
                return MultiPoint(parts)
            return GeometryCollection(parts)

        # Otherwise search children (e.g. parent is Placemark)
        poly_node = parent.find(tag_fn("Polygon"))
        if poly_node is not None:
            return self._parse_polygon(poly_node, tag_fn)

        line_node = parent.find(tag_fn("LineString"))
        if line_node is not None:
            coords_node = line_node.find(tag_fn("coordinates"))
            pts = _parse_coordinates_text(coords_node.text if coords_node is not None else "")
            if len(pts) >= 2:
                return LineString(pts)
            return None

        ring_node = parent.find(tag_fn("LinearRing"))
        if ring_node is not None:
            coords_node = ring_node.find(tag_fn("coordinates"))
            pts = _parse_coordinates_text(coords_node.text if coords_node is not None else "")
            if len(pts) >= 2:
                return LineString(pts)
            return None

        point_node = parent.find(tag_fn("Point"))
        if point_node is not None:
            coords_node = point_node.find(tag_fn("coordinates"))
            pts = _parse_coordinates_text(coords_node.text if coords_node is not None else "")
            if pts:
                return Point(pts[0])
            return None

        mg_node = parent.find(tag_fn("MultiGeometry"))
        if mg_node is not None:
            return self._parse_kml_geometry(mg_node, tag_fn)

        return None

    def _parse_polygon(self, poly_node: standard_ET.Element, tag_fn: Any) -> Polygon | None:
        """Parse KML Polygon outerBoundaryIs and all innerBoundaryIs (holes)."""
        # Outer ring
        outer_node = poly_node.find(f".//{tag_fn('outerBoundaryIs')}//{tag_fn('coordinates')}")
        if outer_node is None or not outer_node.text:
            return None

        outer_pts = _parse_coordinates_text(outer_node.text)
        if len(outer_pts) < 3:
            return None

        # Ensure outer ring is closed
        if outer_pts[0] != outer_pts[-1]:
            outer_pts.append(outer_pts[0])

        # Inner rings (holes)
        holes: list[list[tuple[float, float]]] = []
        for inner_node in poly_node.findall(
            f".//{tag_fn('innerBoundaryIs')}//{tag_fn('coordinates')}"
        ):
            if inner_node is not None and inner_node.text:
                inner_pts = _parse_coordinates_text(inner_node.text)
                if len(inner_pts) >= 3:
                    if inner_pts[0] != inner_pts[-1]:
                        inner_pts.append(inner_pts[0])
                    holes.append(inner_pts)

        try:
            return Polygon(outer_pts, holes)
        except Exception as e:
            logger.warning("Error constructing polygon: %s", e)
            return None
