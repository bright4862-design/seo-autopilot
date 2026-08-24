#!/usr/bin/env python3
"""Isolated live reproduction of the repair-persistence blocker.

This script performs scanner/review work only. It does not call Base44, create a
ScanRun, persist authority, or use customer credentials. Output is deliberately
bounded to non-secret repair invariant diagnostics.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.indexability_postprocess import apply_indexability_quality_to_result
from app.main import enforce_scan_response_page_budget
from app.render_evidence_quality import apply_render_evidence_quality
from app.repair_contract_v2 import (
    _normalize_canonical_repair_evidence,
    _safe_repair_diagnostic,
    apply_canonical_repair_contract,
)
from app.repair_coverage import first_failed_repair_invariant
from app.repair_shadow_calibration import build_calibrated_shadow_review_analysis
from app.review import run_review
from app.review_calibration import apply_review_evidence_calibration
from app.scanner import run_scan
from app.trust_discovery import apply_trust_discovery_gate, enrich_scan_with_trust_pages
from app.coverage_authority import attach_coverage_authority_evidence
from app.evidence_quality import apply_evidence_quality_gate

TARGETS = {
    "tiqets": "https://www.tiqets.com/",
    "airbnb": "https://www.airbnb.com/",
}


def _pages(result: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _build_precanonical_review(scan_result: dict[str, Any]) -> dict[str, Any]:
    review = run_review(scan_result)
    review = apply_trust_discovery_gate(review, scan_result)
    review = apply_review_evidence_calibration(review, scan_result)
    review = apply_evidence_quality_gate(review, scan_result)
    review = attach_coverage_authority_evidence(review, scan_result)
    return review


async def reproduce(name: str) -> int:
    url = TARGETS[name]
    result = await run_scan(
        website_url=url,
        path_prefix="",
        scan_mode="advanced",
        concurrency=8,
        timeout_seconds=120.0,
        job_mode=True,
    )
    if result.get("success") is not True:
        print(json.dumps({
            "event": "live_repair_repro_scan_failed",
            "target": name,
            "error_class": str(result.get("error_code") or result.get("error") or "scan_failed")[:160],
            "pages_found": int(result.get("pages_found") or 0),
            "pages_crawled": int(result.get("pages_crawled") or 0),
        }, sort_keys=True))
        return 2

    try:
        result = await asyncio.wait_for(enrich_scan_with_trust_pages(result), timeout=7.0)
    except asyncio.TimeoutError:
        pass
    result = apply_indexability_quality_to_result(result)
    result = apply_render_evidence_quality(result)
    result = enforce_scan_response_page_budget(result, "advanced")

    pages = _pages(result)
    review = _build_precanonical_review(result)
    analysis = build_calibrated_shadow_review_analysis(review, pages)
    proposed = analysis.get("proposed_fixes") if isinstance(analysis, dict) else None
    if not isinstance(proposed, list):
        print(json.dumps({
            "event": "live_repair_repro_no_proposed_fixes",
            "target": name,
            "pages_found": int(result.get("pages_found") or 0),
            "pages_crawled": int(result.get("pages_crawled") or len(pages)),
        }, sort_keys=True))
        return 3

    failures: list[dict[str, Any]] = []
    for rank, raw_fix in enumerate(proposed, start=1):
        if not isinstance(raw_fix, dict):
            failures.append({"invariant": "repair_missing", "canonical_action_rank": rank})
            continue
        canonical = _normalize_canonical_repair_evidence(raw_fix, pages)
        failed = first_failed_repair_invariant(canonical)
        if failed:
            failures.append(_safe_repair_diagnostic(canonical, failed, rank=rank))

    contracted = apply_canonical_repair_contract(review, result)
    print(json.dumps({
        "event": "live_repair_repro_result",
        "target": name,
        "pages_found": int(result.get("pages_found") or 0),
        "pages_crawled": int(result.get("pages_crawled") or len(pages)),
        "proposed_fix_count": len(proposed),
        "canonical_repairs_present": isinstance(contracted.get("canonical_repairs"), list),
        "canonical_repair_count": len(contracted.get("canonical_repairs") or []),
        "failed_repair_count": len(failures),
        "failures": failures[:10],
    }, sort_keys=True))
    return 1 if failures else 0


def main() -> int:
    name = (sys.argv[1] if len(sys.argv) > 1 else "tiqets").strip().lower()
    if name not in TARGETS:
        raise SystemExit(f"target must be one of: {', '.join(sorted(TARGETS))}")
    return asyncio.run(reproduce(name))


if __name__ == "__main__":
    raise SystemExit(main())
