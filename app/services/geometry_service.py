"""Geometry normalization, Z-stripping, and topological validation/repair service."""

import shapely
from shapely.validation import explain_validity

from app.core.logging import get_logger

logger = get_logger(__name__)


def clean_and_repair_geometry(
    geom: shapely.Geometry | None,
) -> tuple[shapely.Geometry | None, bool, str | None]:
    """Normalize geometry to 2D, validate topology, and attempt repair via shapely.make_valid.

    Returns:
        tuple of (repaired_geometry, was_repaired_bool, repair_note_string)
    """
    if geom is None:
        return None, False, "Geometry is null"

    if geom.is_empty:
        return geom, False, "Geometry is empty"

    # 1. Force 2D: drop Z and M dimensions for surface measurement
    geom_2d = shapely.force_2d(geom)

    # 2. Check topological validity
    if geom_2d.is_valid:
        return geom_2d, False, None

    # Invalid geometry (e.g. self-intersecting polygon ring)
    reason = explain_validity(geom_2d)
    logger.info("Attempting topological repair on invalid geometry (%s)", reason)

    try:
        # Shapely 2.0 make_valid resolves bowties, overlapping rings, and self-intersections
        repaired = shapely.make_valid(geom_2d)
        if repaired is not None and not repaired.is_empty and repaired.is_valid:
            note = f"Repaired invalid topology ({reason}) using make_valid"
            return repaired, True, note

        return geom_2d, False, f"Invalid geometry could not be repaired: {reason}"
    except Exception as e:
        logger.warning("Error during geometry repair: %s", e)
        return geom_2d, False, f"Repair failed: {e}"
