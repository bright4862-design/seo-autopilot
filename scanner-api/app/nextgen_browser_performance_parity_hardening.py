"""Contract-bound hardening for Lane-C raw/rendered critical-content parity.

This module is additive and pure. It normalizes document-relative canonical URLs
before calling the existing parity comparator, validates the versioned result, and
provides a contract-bound coverage aggregate. It performs no rendering, network
I/O, persistence, scoring, or execution-budget decisions.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.nextgen_browser_performance import (
    CRITICAL_PARITY_VERSION,
    compare_critical_content_parity,
)
from app.nextgen_browser_performance_contract import (
    INTEGRITY_VERSION,
    validate_critical_parity_contract,
    validate_representative_sample_contract,
)
from app.nextgen_browser_performance_coverage import (
    summarize_critical_parity_coverage,
)

RESOLVED_CRITICAL_PARITY_VERSION = "nextgen_critical_content_parity_v2_resolved"
RESOLVED_CRITICAL_PARITY_INTEGRITY_VERSION = (
    "nextgen_critical_content_parity_v2_resolved_integrity_v1"
)
BOUND_PARITY_COVERAGE_VERSION = "nextgen_browser_parity_coverage_v2_contract_bound"
CANONICAL_RESOLUTION_VERSION = "document_identity_v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _document_identity(page: Any) -> str | None:
    if not isinstance(page, dict):
        return None
    raw = _text(page.get("final_url") or page.get("url"))
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.query,
        "",
    ))


def _resolved_canonical(page: Any) -> Any:
    if not isinstance(page, dict) or "canonical" not in page:
        return None
    raw = page.get("canonical")
    text = _text(raw)
    if not text:
        return raw
    base = _document_identity(page)
    if not base:
        return raw
    resolved = urljoin(base, text)
    try:
        parsed = urlsplit(resolved)
    except Exception:
        return raw
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return raw
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.query,
        "",
    ))


def _page_with_resolved_canonical(page: Any) -> Any:
    if not isinstance(page, dict):
        return page
    clone = deepcopy(page)
    if "canonical" in clone:
        clone["canonical"] = _resolved_canonical(clone)
    return clone


def compare_critical_content_parity_resolved(
    raw_page: dict[str, Any],
    rendered_page: dict[str, Any] | None,
    *,
    render_state: str = "completed",
    render_reason: str | None = None,
) -> dict[str, Any]:
    """Compare critical content with document-relative canonicals normalized first.

    The existing comparator remains authoritative for raw/render identity,
    usability, extractor-presence, and critical-field semantics. This wrapper only
    makes canonical comparison browser-correct for relative/protocol-relative
    hrefs and publishes a new additive evidence version.
    """
    raw = _page_with_resolved_canonical(raw_page)
    rendered = _page_with_resolved_canonical(rendered_page)
    result = compare_critical_content_parity(
        raw,
        rendered,
        render_state=render_state,
        render_reason=render_reason,
    )
    return {
        **result,
        "version": RESOLVED_CRITICAL_PARITY_VERSION,
        "base_version": CRITICAL_PARITY_VERSION,
        "canonical_resolution_version": CANONICAL_RESOLUTION_VERSION,
    }


def validate_resolved_critical_parity_contract(evidence: Any) -> dict[str, Any]:
    """Validate the resolved parity envelope and the underlying v1 parity contract."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {
            "version": RESOLVED_CRITICAL_PARITY_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }
    if evidence.get("version") != RESOLVED_CRITICAL_PARITY_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("base_version") != CRITICAL_PARITY_VERSION:
        reasons.append("base_version_mismatch")
    if evidence.get("canonical_resolution_version") != CANONICAL_RESOLUTION_VERSION:
        reasons.append("canonical_resolution_version_mismatch")

    base = deepcopy(evidence)
    base["version"] = CRITICAL_PARITY_VERSION
    base.pop("base_version", None)
    base.pop("canonical_resolution_version", None)
    base_result = validate_critical_parity_contract(base)
    if not base_result.get("valid"):
        reasons.extend(
            f"base:{reason}" for reason in base_result.get("reasons", [])
        )
    return {
        "version": RESOLVED_CRITICAL_PARITY_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }


def _coverage_blank(
    reason: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": BOUND_PARITY_COVERAGE_VERSION,
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
        "parity_version": RESOLVED_CRITICAL_PARITY_VERSION,
        "contract_binding": INTEGRITY_VERSION,
        "details": details or {},
    }


def summarize_resolved_critical_parity_coverage(
    sample: Any,
    parity_results: Any,
) -> dict[str, Any]:
    """Count coverage only after sample and every parity result pass contracts.

    This prevents structurally forged or stale parity dictionaries from being
    credited as completed browser evidence. Foreign/duplicate URL binding remains
    delegated to the existing coverage helper after version-safe validation.
    """
    sample_result = validate_representative_sample_contract(sample)
    if not sample_result.get("valid"):
        return _coverage_blank(
            "sample_contract_invalid",
            details={"sample_reasons": sample_result.get("reasons", [])},
        )
    if not isinstance(parity_results, list):
        return _coverage_blank("parity_results_not_list")

    malformed: list[dict[str, Any]] = []
    legacy_rows: list[dict[str, Any]] = []
    for index, result in enumerate(parity_results):
        contract = validate_resolved_critical_parity_contract(result)
        if not contract.get("valid"):
            malformed.append({
                "index": index,
                "reasons": contract.get("reasons", []),
            })
            continue
        legacy = deepcopy(result)
        legacy["version"] = CRITICAL_PARITY_VERSION
        legacy.pop("base_version", None)
        legacy.pop("canonical_resolution_version", None)
        legacy_rows.append(legacy)

    if malformed:
        return _coverage_blank(
            "parity_contract_invalid",
            details={"malformed_results": malformed},
        )

    coverage = summarize_critical_parity_coverage(sample, legacy_rows)
    return {
        **coverage,
        "version": BOUND_PARITY_COVERAGE_VERSION,
        "parity_version": RESOLVED_CRITICAL_PARITY_VERSION,
        "contract_binding": INTEGRITY_VERSION,
    }
