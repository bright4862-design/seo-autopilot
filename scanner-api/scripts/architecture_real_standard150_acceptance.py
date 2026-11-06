"""Isolated real-site Standard-150 shadow architecture acceptance.

This calls only the in-process scanner and read-only public URLs. It does not
submit a Base44 customer scan, write a FixList, or activate production ranking.
Robots policy and Standard-150's existing 75s budget are enforced by run_scan.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import json
from pathlib import Path
import sys

from app.scanner import run_scan
from app.repair_architecture_priority import page_role
from app.repair_priority_calibration import annotate_calibrated_repair_priority

TARGETS = {
    "marketplace": "https://www.funbooker.com/",
    "mixed_index": "https://crawlcheck.io/",
}


def _url(page):
    return str(page.get("url") or page.get("final_url") or page.get("page_url") or "")


def _issue(page):
    return {
        "rule": "canonical_missing",
        "category": "canonical",
        "priority": "medium",
        "technical_severity": "medium",
        "evidence_class": "confirmed_problem",
        "page_template_family": str(page.get("page_template_family") or "mixed"),
        "affected_pages": [_url(page)],
    }


async def run_one(name, target):
    result = await run_scan(target, scan_mode="standard_150", concurrency=3)
    pages = [p for p in result.get("pages", []) if isinstance(p, dict)]
    counts = Counter(page_role(p) for p in pages)
    report = {
        "site": name, "mode": "standard_150",
        "success": bool(result.get("success")),
        "pages_crawled": len(pages),
        "roles": dict(counts),
        "scanner_version": str(result.get("version") or ""),
        "scope": "read_only_branch_ci",
    }
    # Standard 150 is a *maximum*, not a requirement that 150 URLs resolve.
    # These two selected large-site targets must yield a broad observed cohort,
    # but 149/150 is valid and must not be mistaken for a scanner regression.
    if not result.get("success") or not 140 <= len(pages) <= 150:
        report["gate"] = "NO_GO_INSUFFICIENT_BREADTH_OR_BUDGET"
        return report

    structural = next((p for p in pages if page_role(p) == "structural" and p.get("indexable") is not False and _url(p)), None)
    ordinary = next((p for p in pages if page_role(p) in {"commercial_leaf", "support", "other"} and p.get("indexable") is not False and _url(p)), None)
    if not structural or not ordinary:
        report["gate"] = "NO_GO_ROLE_PAIR_ABSENT"
        return report

    structural_fix = annotate_calibrated_repair_priority(_issue(structural), pages)
    ordinary_fix = annotate_calibrated_repair_priority(_issue(ordinary), pages)
    report["priority"] = {
        "structural_band": structural_fix["action_priority"],
        "ordinary_band": ordinary_fix["action_priority"],
        "structural_score": structural_fix["action_priority_score"],
        "ordinary_score": ordinary_fix["action_priority_score"],
        "structural_role_count": structural_fix["priority_context"]["architecture_role_counts"]["structural"],
        "architecture_version": structural_fix["priority_context"]["architecture_priority_version"],
    }
    if (structural_fix["base_severity"] != ordinary_fix["base_severity"]
        or structural_fix["action_priority"] != ordinary_fix["action_priority"]
        or structural_fix["action_priority_score"] <= ordinary_fix["action_priority_score"]):
        report["gate"] = "NO_GO_PRIORITY_REGRESSION"
    else:
        report["gate"] = "PASS_REAL_PAGE_SHADOW_ORDER"
    return report


async def main():
    reports = []
    for name, url in TARGETS.items():
        reports.append(await run_one(name, url))
        print(json.dumps(reports[-1], sort_keys=True), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/architecture-standard150-real.json").write_text(
        json.dumps(reports, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if all(item["gate"].startswith("PASS_") for item in reports) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
