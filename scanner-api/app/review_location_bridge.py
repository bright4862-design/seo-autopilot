from __future__ import annotations

from typing import Any

from .location_template_content import build_location_template_raw_fixes


def add_location_template_raw_fixes(
    body: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a shallow scan-payload copy with bounded location repairs prepended."""
    location_fixes = build_location_template_raw_fixes(pages)
    if not location_fixes:
        return body

    patched = dict(body)
    existing = body.get("raw_fixes") if isinstance(body.get("raw_fixes"), list) else []
    patched["raw_fixes"] = location_fixes + [
        item for item in existing if isinstance(item, dict)
    ]
    return patched
