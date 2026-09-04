from __future__ import annotations

from typing import Any

from . import review_core as _core
from .review_location_bridge import add_location_template_raw_fixes

# Re-export the existing review surface unchanged. The implementation stays in
# review_core; only run_review is wrapped so location-template evidence can join
# the same raw-fix normalization/scoring path as every other finding.
for _name, _value in vars(_core).items():
    if not _name.startswith("__") and _name != "run_review":
        globals()[_name] = _value


def run_review(payload: dict[str, Any]) -> dict[str, Any]:
    body = _core.unwrap_scan_payload(payload)
    pages = _core.first_array(
        body.get("crawled_pages"),
        body.get("pages"),
        body.get("scanned_pages"),
        body.get("crawl_pages"),
        _core.deep_get(body, "technical_audit_summary", "pages"),
    )
    return _core.run_review(add_location_template_raw_fixes(body, pages))
