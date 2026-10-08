"""Identifier generation and filename sanitization utilities."""

import os
import re
import uuid


def generate_file_id() -> str:
    """Generate a clean, collision-resistant 12-character hex ID (e.g. 'a1b2c3d4e5f6')."""
    return uuid.uuid4().hex[:12]


def sanitize_filename(filename: str | None) -> str:
    """Sanitize user-provided filename to prevent directory traversal and shell hazards.

    Strips directory components, control characters, and leading/trailing dots/spaces.
    """
    if not filename:
        return "unnamed_file"

    # Strip directory paths across OS platforms
    cleaned = os.path.basename(filename.replace("\\", "/"))

    # Replace null bytes and non-printable control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", cleaned)

    # Disallow dangerous names like '.' or '..'
    cleaned = cleaned.strip(". ")
    if not cleaned:
        return "unnamed_file"

    # Limit filename length
    if len(cleaned) > 255:
        base, ext = os.path.splitext(cleaned)
        cleaned = base[: 255 - len(ext)] + ext

    return cleaned
