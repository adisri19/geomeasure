"""Shapefile reader utilizing pyogrio/GDAL with safe coordinate and attribute decoding."""

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyogrio.raw
import pyproj
import shapely

from app.core.errors import CrsUndefinedException, NoFeaturesException
from app.core.logging import get_logger
from app.services.readers.base import BaseReader, FileMetadata, RawFeature
from app.services.zip_handler import DiscoveredShapefile, SafeZipExtractor

logger = get_logger(__name__)


def _sanitize_attribute_value(val: Any) -> Any:
    """Recursively convert NumPy/pandas/date objects into JSON-compliant Python types."""
    if val is None:
        return None
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, np.datetime64):
        # Check for NaT
        if np.isnat(val):
            return None
        # Convert to ISO format string
        return str(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return val.decode("latin-1")
            except Exception:
                return val.hex()
    if isinstance(val, (list, tuple, np.ndarray)):
        return [_sanitize_attribute_value(item) for item in val]
    if isinstance(val, dict):
        return {str(k): _sanitize_attribute_value(v) for k, v in val.items()}
    return str(val) if not isinstance(val, (bool, str)) else val


class ShapefileReader(BaseReader):
    """Reader for Shapefile datasets (.shp + companions)."""

    def read(self, path: Path) -> tuple[FileMetadata, list[RawFeature]]:
        """Read all discovered shapefiles in directory or a direct .shp file.

        Args:
            path: Extraction directory path or direct .shp file path.

        Returns:
            Tuple of (FileMetadata, list of RawFeature).
        """
        discovered: list[DiscoveredShapefile] = []
        if path.is_file() and path.suffix.lower() == ".shp":
            # Direct shp path
            folder = path.parent
            base = path.stem.lower()
            files = {f.name.lower(): f for f in folder.iterdir() if f.is_file()}
            discovered.append(
                DiscoveredShapefile(
                    name=path.stem,
                    shp_path=path,
                    shx_path=files[f"{base}.shx"],
                    dbf_path=files[f"{base}.dbf"],
                    prj_path=files.get(f"{base}.prj"),
                    cpg_path=files.get(f"{base}.cpg"),
                )
            )
        else:
            # Directory of extracted shapefiles
            discovered = SafeZipExtractor._discover_shapefiles(path)

        all_raw_features: list[RawFeature] = []
        layer_names: list[str] = []
        warnings: list[str] = []
        discovered_crss: list[str] = []
        any_crs_assumed = False
        primary_crs_wkt: str | None = None

        global_feature_index = 0

        for shp_item in discovered:
            layer_name = shp_item.name
            layer_names.append(layer_name)

            # Determine encoding if .cpg exists
            encoding = "UTF-8"
            if shp_item.cpg_path and shp_item.cpg_path.exists():
                try:
                    cpg_text = shp_item.cpg_path.read_text(errors="ignore").strip()
                    if cpg_text:
                        encoding = cpg_text
                except Exception as e:
                    logger.warning("Could not read .cpg for %s: %s", layer_name, e)

            # Read dataset via pyogrio raw
            try:
                meta, fids, geom_bytes_arr, field_data = pyogrio.raw.read(
                    str(shp_item.shp_path),
                    return_fids=True,
                    encoding=encoding,
                )
            except Exception as e:
                # Retry with latin-1 fallback encoding
                logger.warning(
                    "Pyogrio failed with encoding %s for %s (%s). Retrying with latin-1",
                    encoding,
                    layer_name,
                    e,
                )
                meta, fids, geom_bytes_arr, field_data = pyogrio.raw.read(
                    str(shp_item.shp_path),
                    return_fids=True,
                    encoding="latin-1",
                )

            fields = list(meta.get("fields", []))
            num_features = len(fids)

            # 1. Determine CRS for this shapefile
            layer_crs, crs_wkt, is_assumed, crs_warn = self._resolve_layer_crs(
                shp_item=shp_item,
                meta_crs=meta.get("crs"),
                geom_bytes_arr=geom_bytes_arr,
            )
            discovered_crss.append(layer_crs)
            if is_assumed:
                any_crs_assumed = True
            if crs_warn:
                warnings.append(crs_warn)
            if primary_crs_wkt is None and crs_wkt:
                primary_crs_wkt = crs_wkt

            # 2. Parse features
            for i in range(num_features):
                fid = str(fids[i]) if fids is not None else str(i)
                wkb = geom_bytes_arr[i] if geom_bytes_arr is not None else None

                # Convert geometry
                geom: shapely.Geometry | None = None
                geom_type = "None"
                if wkb is not None and len(wkb) > 0:
                    try:
                        parsed_geom = shapely.from_wkb(wkb)
                        if parsed_geom is not None and not parsed_geom.is_empty:
                            geom = shapely.force_2d(parsed_geom)
                            geom_type = geom.geom_type
                        else:
                            geom_type = "None"
                    except Exception as e:
                        logger.warning("Failed to decode WKB for feature fid=%s: %s", fid, e)
                        geom = None
                        geom_type = "None"

                # Extract and sanitize attributes
                props: dict[str, Any] = {}
                for f_idx, field_name in enumerate(fields):
                    val = field_data[f_idx][i]
                    props[str(field_name)] = _sanitize_attribute_value(val)

                all_raw_features.append(
                    RawFeature(
                        feature_index=global_feature_index,
                        source_feature_id=fid,
                        layer_name=layer_name,
                        geometry=geom,
                        properties=props,
                        crs=layer_crs,
                        geometry_type=geom_type,
                    )
                )
                global_feature_index += 1

        if not all_raw_features:
            raise NoFeaturesException("Shapefile contains zero feature records")

        # Determine unified file-level CRS
        unique_crss = list(dict.fromkeys(discovered_crss))
        if len(unique_crss) == 1:
            file_crs = unique_crss[0]
        else:
            file_crs = "MIXED"
            warnings.append(
                f"Multiple shapefile layers with differing CRSs detected: {', '.join(unique_crss)}"
            )

        file_metadata = FileMetadata(
            crs=file_crs,
            crs_wkt=primary_crs_wkt,
            crs_assumed=any_crs_assumed,
            layer_names=layer_names,
            feature_count=len(all_raw_features),
            warnings=warnings,
        )

        return file_metadata, all_raw_features

    def _resolve_layer_crs(
        self,
        shp_item: DiscoveredShapefile,
        meta_crs: Any,
        geom_bytes_arr: np.ndarray,
    ) -> tuple[str, str | None, bool, str | None]:
        """Resolve layer CRS from .prj or coordinate bounding box heuristic."""
        # 1. Check if .prj file exists
        if shp_item.prj_path and shp_item.prj_path.exists():
            try:
                prj_content = shp_item.prj_path.read_text(errors="ignore").strip()
                if prj_content:
                    crs = pyproj.CRS.from_user_input(prj_content)
                    epsg = crs.to_epsg(min_confidence=70)
                    if epsg is not None:
                        return f"EPSG:{epsg}", crs.to_wkt(), False, None
                    # Fallback to authority
                    auth = crs.to_authority()
                    if auth:
                        return f"{auth[0]}:{auth[1]}", crs.to_wkt(), False, None
                    # Fallback to name or WKT
                    name = crs.name or "Unknown Projected"
                    return name, crs.to_wkt(), False, None
            except Exception as e:
                logger.warning("Error parsing .prj for %s: %s", shp_item.name, e)

        # 2. Check pyogrio metadata CRS if prj parsing did not succeed
        if meta_crs:
            try:
                crs = pyproj.CRS.from_user_input(meta_crs)
                epsg = crs.to_epsg(min_confidence=70)
                if epsg is not None:
                    return f"EPSG:{epsg}", crs.to_wkt(), False, None
                auth = crs.to_authority()
                if auth:
                    return f"{auth[0]}:{auth[1]}", crs.to_wkt(), False, None
                return crs.name or "Unknown", crs.to_wkt(), False, None
            except Exception as e:
                logger.warning("Error resolving pyogrio meta CRS: %s", e)

        # 3. No .prj found - apply coordinate bounding box inspection heuristic
        min_x, min_y, max_x, max_y = float("inf"), float("inf"), float("-inf"), float("-inf")
        has_coords = False

        for wkb in geom_bytes_arr:
            if wkb is not None and len(wkb) > 0:
                try:
                    g = shapely.from_wkb(wkb)
                    if g is not None and not g.is_empty:
                        bounds = g.bounds  # (minx, miny, maxx, maxy)
                        min_x = min(min_x, bounds[0])
                        min_y = min(min_y, bounds[1])
                        max_x = max(max_x, bounds[2])
                        max_y = max(max_y, bounds[3])
                        has_coords = True
                except Exception:
                    pass

        if (
            has_coords
            and (-180.0 <= min_x <= 180.0)
            and (-180.0 <= max_x <= 180.0)
            and (-90.0 <= min_y <= 90.0)
            and (-90.0 <= max_y <= 90.0)
        ):
            # Coordinates fall within geographic limits
            warning = (
                f"Shapefile '{shp_item.name}' lacks a .prj file. All coordinates lie within "
                "geographic bounds [-180, 180] and [-90, 90], so EPSG:4326 (WGS 84) was assumed."
            )
            return "EPSG:4326", None, True, warning

        # Outside geographic range and missing .prj
        raise CrsUndefinedException(
            message=(
                f"Shapefile '{shp_item.name}' has no .prj file and coordinates lie outside geographic bounds "
                f"[-180, 180], [-90, 90] (bounds: x=[{min_x:.2f}, {max_x:.2f}], y=[{min_y:.2f}, {max_y:.2f}]). "
                "A projected coordinate system is required."
            ),
            details={"shapefile": shp_item.name, "bounds": [min_x, min_y, max_x, max_y]},
        )
