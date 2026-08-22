"""One canonical scope/family pass over a repair's affected evidence.

Twenty of the thirty completed audit scans shipped a ratio drawn from two
different URL sets. Suppressing those ratios stops the lie but tells the
customer nothing: 126 orphaned URLs spanning workshops, categories and articles
are not one repair against one family, they are partitions, and the breakdown is
what makes any of them actionable.

Two rules this module exists to enforce:

The family comes from the family already stamped on authoritative page evidence.
Re-deriving it from the path here would be a second opinion competing with the
crawl's own classification -- the same split that Patch C removed for coverage.

The affected evidence decides the scope, not the representative. Production
picked a representative first and let its family become the group's family,
which is precisely how a mixed group came to be labelled Homepage.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

REPAIR_COVERAGE_VERSION = "repair_coverage_v1_family_consistent"

UNKNOWN_FAMILY = "unknown"

# Families that are labels for "no single family", never a real one.
NON_SPECIFIC_FAMILIES = frozenset({"", "mixed", "sitewide", "cross_cutting", UNKNOWN_FAMILY})

# Access and crawler-failure evidence groups by failure mode, not page template.
CROSS_CUTTING_RULES = frozenset({"rate_limited_page", "broken_page", "server_error", "blocked_page"})

DEFAULT_MAX_AFFECTED = 150


def evidence_url_key(value: Any) -> str:
    """Path-only identity, which is what template family is defined over.

    Deliberately narrow: query and fragment do not change a page's template, and
    including them here would fragment a family that is really one family.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = urlsplit(raw).path if "//" in raw else raw.split("?")[0].split("#")[0]
    path = path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/"


def _page_family(page: dict[str, Any], resolver: Any = None) -> str:
    """The family this page already carries, reconciled to one vocabulary.

    Page evidence can carry a legacy family name while detectors emit the
    current one. Reading the raw stamp would silently downgrade a family rather
    than reclassify it, so the caller supplies the reconciler review already
    uses; this module never derives a family from a path itself.
    """
    stamped = page.get("page_template_family")
    if resolver is not None:
        family = str(resolver(stamped, page.get("final_url") or page.get("url") or page.get("path")) or "").strip().lower()
    else:
        family = str(stamped or "").strip().lower()
    return family if family and family not in NON_SPECIFIC_FAMILIES else UNKNOWN_FAMILY


def _is_cross_cutting(fix: dict[str, Any]) -> bool:
    if str(fix.get("source", "")).startswith("scanner_verified_failed_pages:"):
        return True
    return str(fix.get("rule", "")) in CROSS_CUTTING_RULES


def normalize_repair_scope(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    *,
    family_resolver: Any = None,
    max_affected: int = DEFAULT_MAX_AFFECTED,
) -> dict[str, Any]:
    """Return a copy of `fix` with scope, family and partitions derived from evidence."""
    normalized = dict(fix or {})

    stamped: dict[str, str] = {}
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        key = evidence_url_key(page.get("final_url") or page.get("url") or page.get("path"))
        if key and key not in stamped:
            stamped[key] = _page_family(page, family_resolver)

    # Deduplicate by evidence identity while keeping the detector's order, so a
    # repeated URL cannot inflate the count the customer is shown.
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for raw in normalized.get("affected_pages") or []:
        key = evidence_url_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append((key, str(raw)))

    breakdown: dict[str, int] = {}
    representatives: dict[str, str] = {}
    for key, raw in ordered:
        family = stamped.get(key, UNKNOWN_FAMILY)
        breakdown[family] = breakdown.get(family, 0) + 1
        representatives.setdefault(family, raw)

    page_count = len(ordered)
    kept = [raw for _, raw in ordered[:max_affected]]

    explicit_scope = str(normalized.get("page_scope") or "").strip().lower()
    known_families = [family for family in breakdown if family != UNKNOWN_FAMILY]

    if explicit_scope == "sitewide":
        # An explicit sitewide claim carries its own proof and is preserved.
        scope, family = "sitewide", str(normalized.get("page_template_family") or "")
    elif _is_cross_cutting(normalized):
        scope, family = "cross_cutting", "mixed"
    elif page_count == 0:
        scope, family = "page", UNKNOWN_FAMILY
    elif len(breakdown) == 1 and len(known_families) == 1:
        scope = "page" if page_count == 1 else "family"
        family = known_families[0]
    else:
        # More than one family, or an unaccounted URL, means there is no single
        # family this repair belongs to. Naming one would be an assertion the
        # evidence does not support.
        scope, family = "mixed", "mixed"

    normalized.update({
        "page_scope": scope,
        "page_template_family": family,
        "affected_pages": kept,
        "page_count": page_count,
        "family_breakdown": breakdown,
        "representative_pages_by_family": representatives,
        # A truncated list must never be compared against a total; downstream
        # suppresses the ratio rather than dividing a sample by a whole.
        "affected_pages_complete": page_count <= max_affected,
        "repair_coverage_version": REPAIR_COVERAGE_VERSION,
    })
    return normalized
