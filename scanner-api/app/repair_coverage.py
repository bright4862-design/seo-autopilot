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
from urllib.parse import quote, unquote, unquote_to_bytes, urlsplit

REPAIR_COVERAGE_VERSION = "repair_coverage_v1_family_consistent"

UNKNOWN_FAMILY = "unknown"

# Families that are labels for "no single family", never a real one.
NON_SPECIFIC_FAMILIES = frozenset({"", "mixed", "sitewide", "cross_cutting", UNKNOWN_FAMILY})

# Access and crawler-failure evidence groups by failure mode, not page template.
CROSS_CUTTING_RULES = frozenset({"rate_limited_page", "broken_page", "server_error", "blocked_page"})

DEFAULT_MAX_AFFECTED = 150


# Parameters that identify a visitor or a campaign, never a page. Two URLs
# differing only by these are the same evidence.
TRACKING_PARAMETERS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "mc_cid", "mc_eid",
    "ref", "referrer", "source",
})


def _normalized_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = urlsplit(raw).path if "//" in raw else raw.split("?")[0].split("#")[0]
    path = unquote(path) or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    # Case folded because a host filesystem is not the identity of a page, and
    # /Doc.PDF and /doc.pdf were the same page in every production sample.
    return (path.rstrip("/") or "/").lower()


def template_family_key(value: Any) -> str:
    """Path-only identity, which is what a template family is defined over.

    Deliberately narrow: a query string does not change a page's template, so
    including it here would split one family into many.
    """
    return _normalized_path(value)


def _safe_query_decode(value: str) -> str:
    """Mirror decodeURIComponent: percent-decode UTF-8, but never treat + as space."""
    try:
        return unquote_to_bytes(value).decode("utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError):
        return value


def _encode_query_component(value: str) -> str:
    # encodeURIComponent leaves exactly these punctuation characters unescaped.
    return quote(value, safe="-_.!~*'()")


def _canonical_query(value: Any) -> str:
    """Sorted, tracking-free query, byte-compatible with Base44 JavaScript."""
    raw = str(value or "")
    query = urlsplit(raw).query if "//" in raw else (raw.split("?", 1)[1].split("#")[0] if "?" in raw else "")
    if not query:
        return ""

    pairs: list[tuple[str, str]] = []
    for part in query.split("&"):
        if not part:
            continue
        key_raw, separator, val_raw = part.partition("=")
        key = _safe_query_decode(key_raw)
        value = _safe_query_decode(val_raw if separator else "")
        if key.lower() not in TRACKING_PARAMETERS:
            pairs.append((key, value))
    if not pairs:
        return ""

    # Duplicate keys are kept, both of them: dropping one would merge two pages
    # that a server may well render differently.
    pairs.sort()
    return "&".join(
        f"{_encode_query_component(key)}={_encode_query_component(value)}"
        for key, value in pairs
    )


def evidence_url_key(value: Any) -> str:
    """Path plus canonical query: the identity of one piece of page evidence."""
    path = _normalized_path(value)
    if not path:
        return ""
    query = _canonical_query(value)
    return f"{path}?{query}" if query else path


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
        key = template_family_key(page.get("final_url") or page.get("url") or page.get("path"))
        if key and key not in stamped:
            stamped[key] = _page_family(page, family_resolver)

    # Deduplicate by evidence identity while keeping the detector's order, so a
    # repeated URL cannot inflate the count the customer is shown. Family lookup
    # remains path-only because query parameters do not change a page template.
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for raw in normalized.get("affected_pages") or []:
        family_key = template_family_key(raw)
        evidence_key = evidence_url_key(raw)
        if not family_key or not evidence_key or evidence_key in seen:
            continue
        seen.add(evidence_key)
        ordered.append((family_key, str(raw)))

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


def _count(value: Any) -> int:
    """Mirror JavaScript Number()+Math.trunc used by the Base44 invariant."""
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _optional_count(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _unique_affected_evidence(repair: dict[str, Any]) -> set[str]:
    values = repair.get("affected_pages") if isinstance(repair.get("affected_pages"), list) else []
    return {key for value in values if (key := evidence_url_key(value))}


def first_failed_repair_invariant(repair: dict[str, Any] | None) -> str:
    """Mirror Base44's fail-closed structural repair-coverage invariant.

    The durable worker runs this after canonical normalization and before the
    signed completion envelope is built. Base44 still re-runs its independent
    JavaScript copy at persistence time; this mirror prevents a payload known to
    be structurally impossible from crossing the worker/Base44 boundary.
    """
    if not isinstance(repair, dict):
        return "repair_missing"

    reported_raw = repair.get("affected_reported")
    reported = _count(repair.get("page_count") if reported_raw is None else reported_raw)
    observed_raw = repair.get("affected_observed")
    observed = _count(reported if observed_raw is None else observed_raw)
    eligible_raw = repair.get("affected_eligible")
    eligible = _count(observed if eligible_raw is None else eligible_raw)
    checked_eligible = _optional_count(repair.get("checked_eligible"))
    indexable_affected = _count(repair.get("indexable_affected"))
    indexable_eligible = _optional_count(repair.get("indexable_checked_eligible"))
    page_count = _count(repair.get("page_count"))
    scope = str(repair.get("page_scope") or "").lower()
    partitions = repair.get("family_breakdown") if isinstance(repair.get("family_breakdown"), dict) else {}
    complete = repair.get("affected_pages_complete") is not False

    cardinalities = [reported, observed, eligible, indexable_affected, page_count]
    if any(value < 0 for value in cardinalities):
        return "negative_cardinality"
    if checked_eligible is not None and checked_eligible < 0:
        return "negative_cardinality"
    if indexable_eligible is not None and indexable_eligible < 0:
        return "negative_cardinality"

    if observed > reported:
        return "affected_observed_exceeds_reported"
    if eligible > observed:
        return "affected_eligible_exceeds_observed"
    if checked_eligible is not None and eligible > checked_eligible:
        return "affected_eligible_exceeds_checked_eligible"
    if indexable_affected > eligible:
        return "indexable_affected_exceeds_eligible"
    if indexable_eligible is not None and checked_eligible is not None and indexable_eligible > checked_eligible:
        return "indexable_checked_eligible_exceeds_checked_eligible"
    if indexable_eligible is not None and indexable_affected > indexable_eligible:
        return "indexable_affected_exceeds_indexable_checked_eligible"

    partition_total = sum(_count(value) for value in partitions.values())
    if partitions and partition_total != page_count:
        return "family_breakdown_does_not_sum_to_page_count"

    if complete and len(_unique_affected_evidence(repair)) != page_count:
        return "page_count_disagrees_with_unique_affected_pages"

    named_families = [family for family in partitions if family not in NON_SPECIFIC_FAMILIES]
    if scope == "page" and page_count > 1:
        return "page_scope_has_multiple_pages"
    if scope == "family" and len(partitions) > 1:
        return "family_scope_spans_multiple_families"
    if scope == "mixed" and len(partitions) < 2:
        return "mixed_scope_without_partitions"

    representatives = repair.get("representative_pages_by_family")
    if isinstance(representatives, dict) and complete:
        affected = _unique_affected_evidence(repair)
        for family, value in representatives.items():
            urls = value if isinstance(value, list) else [value]
            if not urls:
                return "representative_is_not_an_affected_page"
            for url in urls:
                if evidence_url_key(url) not in affected:
                    return "representative_is_not_an_affected_page"
            if named_families and family not in partitions:
                return "representative_family_not_in_breakdown"

    return ""
