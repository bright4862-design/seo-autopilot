"""Fail-closed binding for Lane-C representative performance samples.

The representative sampler is deterministic, but a structurally plausible sample can
still be transported with a different selected population. This helper recomputes the
sample from the caller-supplied authoritative candidate population and requires the
published selection evidence to match exactly before later browser/provider work can
trust it.

No function here performs network I/O, grants a browser/Lighthouse execution budget,
or writes customer/authority state.
"""
from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlsplit

from app.nextgen_browser_performance import (
    REPRESENTATIVE_SAMPLE_VERSION,
    select_representative_performance_pages,
)

SAMPLE_BINDING_VERSION = "nextgen_performance_sample_binding_v1"

_BOUND_FIELDS = (
    "version",
    "requested_max_pages",
    "max_pages",
    "hard_cap",
    "eligible_page_observations",
    "duplicate_page_observations_dropped",
    "eligible_pages",
    "template_families",
    "selected_pages",
    "template_coverage_complete",
    "omitted_template_families",
    "pages",
)


def _absolute_http_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value.strip())
    except Exception:
        return False
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _result(*, valid: bool, reasons: list[str], expected: dict[str, Any] | None = None) -> dict[str, Any]:
    expected_pages = expected.get("pages") if isinstance(expected, dict) else None
    expected_urls = [row.get("url") for row in expected_pages or [] if isinstance(row, dict)]
    return {
        "version": SAMPLE_BINDING_VERSION,
        "contract": REPRESENTATIVE_SAMPLE_VERSION,
        "valid": valid,
        "reasons": sorted(set(reasons)),
        "expected_selected_urls": expected_urls if expected is not None else None,
    }


def validate_representative_sample_binding(
    pages: Iterable[dict[str, Any]],
    sample: Any,
) -> dict[str, Any]:
    """Prove that ``sample`` is the deterministic selection for ``pages``.

    ``pages`` must be the authoritative retained-page population supplied by the
    serialized integrator. This function does not decide that population and does not
    authorize execution of every selected candidate.
    """
    if not isinstance(sample, dict):
        return _result(valid=False, reasons=["sample_not_object"])
    if sample.get("version") != REPRESENTATIVE_SAMPLE_VERSION:
        return _result(valid=False, reasons=["version_mismatch"])

    requested = sample.get("requested_max_pages")
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 0:
        return _result(valid=False, reasons=["requested_max_pages_invalid"])

    try:
        authoritative_pages = list(pages)
    except Exception:
        return _result(valid=False, reasons=["candidate_population_unreadable"])

    try:
        expected = select_representative_performance_pages(
            authoritative_pages,
            max_pages=requested,
        )
    except Exception:
        return _result(valid=False, reasons=["candidate_population_invalid"])

    reasons: list[str] = []
    for field in _BOUND_FIELDS:
        if sample.get(field) != expected.get(field):
            reasons.append(f"{field}_mismatch")

    expected_pages = expected.get("pages") if isinstance(expected.get("pages"), list) else []
    if any(
        not isinstance(row, dict) or not _absolute_http_url(row.get("url"))
        for row in expected_pages
    ):
        reasons.append("selected_identity_not_absolute_http")

    return _result(valid=not reasons, reasons=reasons, expected=expected)
