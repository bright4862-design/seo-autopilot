"""Pure coverage accounting for Lane-C raw/rendered critical-content evidence.

This helper binds already-produced representative sample rows to already-produced
critical parity results. It performs no rendering, provider calls, persistence,
scoring, or customer-Fix creation. Missing observations remain explicitly
unassessed; failed/unverifiable pairs remain failed rather than becoming evidence
of a site defect.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

BROWSER_PARITY_COVERAGE_VERSION = "nextgen_browser_parity_coverage_v1"
REPRESENTATIVE_SAMPLE_VERSION = "nextgen_performance_sample_v1"
CRITICAL_PARITY_VERSION = "nextgen_critical_content_parity_v1"
COMPLETED_PARITY_STATES = {"matched", "material_delta"}
PARITY_STATES = COMPLETED_PARITY_STATES | {"not_verified"}


def _http_identity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    # Preserve path/query identity while normalizing only scheme/host and dropping
    # fragments, matching Lane-C's existing final-URL comparison semantics.
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.query,
        "",
    ))


def _blank(reason: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": BROWSER_PARITY_COVERAGE_VERSION,
        "state": "not_verified",
        "reason": reason,
        "selected_pages": None,
        "completed_pages": None,
        "failed_pages": None,
        "unassessed_pages": None,
        "material_delta_pages": None,
        "completion_ratio": None,
        "selected_urls": [],
        "completed_urls": [],
        "failed_urls": [],
        "unassessed_urls": [],
        "material_delta_urls": [],
        "details": details or {},
    }


def summarize_critical_parity_coverage(sample: Any, parity_results: Any) -> dict[str, Any]:
    """Bind a representative sample to its parity results and disclose coverage.

    ``matched`` and ``material_delta`` rows count as completed paired observations.
    ``not_verified`` rows count as failed/unverifiable attempts. Selected URLs with
    no result remain unassessed. Foreign, duplicate, malformed, or internally
    contradictory result rows fail the aggregate closed so they cannot inflate
    completed coverage.
    """
    if not isinstance(sample, dict):
        return _blank("sample_not_object")
    if sample.get("version") != REPRESENTATIVE_SAMPLE_VERSION:
        return _blank("sample_version_mismatch")
    pages = sample.get("pages")
    if not isinstance(pages, list):
        return _blank("sample_pages_not_list")
    selected_count = sample.get("selected_pages")
    if isinstance(selected_count, bool) or not isinstance(selected_count, int) or selected_count < 0:
        return _blank("sample_selected_count_invalid")
    if selected_count != len(pages):
        return _blank("sample_selected_count_mismatch")

    selected_urls: list[str] = []
    for row in pages:
        if not isinstance(row, dict):
            return _blank("sample_page_not_object")
        identity = _http_identity(row.get("url"))
        if identity is None:
            return _blank("sample_page_identity_invalid")
        selected_urls.append(identity)
    if len(selected_urls) != len(set(selected_urls)):
        return _blank("sample_selected_identity_duplicate")

    if not isinstance(parity_results, list):
        return _blank("parity_results_not_list")

    selected_set = set(selected_urls)
    by_url: dict[str, dict[str, Any]] = {}
    foreign_urls: list[str] = []
    duplicate_urls: list[str] = []
    malformed_indexes: list[int] = []

    for index, result in enumerate(parity_results):
        if not isinstance(result, dict) or result.get("version") != CRITICAL_PARITY_VERSION:
            malformed_indexes.append(index)
            continue
        identity = _http_identity(result.get("url"))
        state = result.get("state")
        if identity is None or state not in PARITY_STATES:
            malformed_indexes.append(index)
            continue
        if identity not in selected_set:
            foreign_urls.append(identity)
            continue
        if identity in by_url:
            duplicate_urls.append(identity)
            continue

        material_delta = result.get("material_delta")
        rendered_identity = _http_identity(result.get("rendered_url")) if result.get("rendered_url") is not None else None
        if state == "matched":
            if material_delta is not False or rendered_identity != identity:
                malformed_indexes.append(index)
                continue
        elif state == "material_delta":
            if material_delta is not True or rendered_identity != identity:
                malformed_indexes.append(index)
                continue
        else:  # not_verified
            if material_delta is not None:
                malformed_indexes.append(index)
                continue
        by_url[identity] = result

    if malformed_indexes or foreign_urls or duplicate_urls:
        return _blank(
            "parity_result_binding_invalid",
            details={
                "malformed_result_indexes": sorted(set(malformed_indexes)),
                "foreign_result_urls": sorted(set(foreign_urls)),
                "duplicate_result_urls": sorted(set(duplicate_urls)),
            },
        )

    completed_urls = [url for url in selected_urls if by_url.get(url, {}).get("state") in COMPLETED_PARITY_STATES]
    failed_urls = [url for url in selected_urls if by_url.get(url, {}).get("state") == "not_verified"]
    unassessed_urls = [url for url in selected_urls if url not in by_url]
    material_delta_urls = [url for url in completed_urls if by_url[url]["state"] == "material_delta"]

    if not selected_urls:
        state = "not_applicable"
        reason = "no_selected_pages"
        completion_ratio = None
    elif len(completed_urls) == len(selected_urls):
        state = "complete"
        reason = "all_selected_pages_verified"
        completion_ratio = 1.0
    else:
        state = "partial"
        reason = "selected_pages_not_fully_verified"
        completion_ratio = len(completed_urls) / len(selected_urls)

    return {
        "version": BROWSER_PARITY_COVERAGE_VERSION,
        "state": state,
        "reason": reason,
        "selected_pages": len(selected_urls),
        "completed_pages": len(completed_urls),
        "failed_pages": len(failed_urls),
        "unassessed_pages": len(unassessed_urls),
        "material_delta_pages": len(material_delta_urls),
        "completion_ratio": completion_ratio,
        "selected_urls": selected_urls,
        "completed_urls": completed_urls,
        "failed_urls": failed_urls,
        "unassessed_urls": unassessed_urls,
        "material_delta_urls": material_delta_urls,
        "details": {},
    }
