from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable


CRAWLER_ACCEPTANCE_VERSION = "crawler_acceptance_v1"
REQUIRED_STRATA = {"smb_cms", "saas_js", "ecommerce_marketplace"}
EXPECTED_SITES_PER_STRATUM = 3
METADATA_NOISE_RULES = {
    "missing_title",
    "missing_meta_description",
    "missing_h1",
    "multiple_h1",
    "image_alt_text",
    "canonical_missing",
    "schema",
}


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _str(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _page_path(page: dict) -> str:
    return _str(page.get("path") or page.get("final_url") or page.get("url") or "/")


def _finding_path(finding: dict) -> str:
    return _str(finding.get("page_url") or (_list(finding.get("affected_pages")) or [""])[0])


def _issue(code: str, detail: str, *, count: int = 1) -> dict[str, Any]:
    return {"code": code, "detail": detail, "count": max(1, int(count or 1))}


def _score_values(review: dict) -> dict[str, int]:
    candidates = {
        "health_score": review.get("health_score"),
        "seo_score": review.get("seo_score"),
        "website_health_report.health_score": _dict(review.get("website_health_report")).get("health_score"),
        "website_health_report.score": _dict(review.get("website_health_report")).get("score"),
        "scan_summary.health_score": _dict(review.get("scan_summary")).get("health_score"),
        "scan_summary.score": _dict(review.get("scan_summary")).get("score"),
    }
    technical = _dict(review.get("technical_audit_summary"))
    if "health_score" in technical:
        candidates["technical_audit_summary.health_score"] = technical.get("health_score")
    if "score" in technical:
        candidates["technical_audit_summary.score"] = technical.get("score")

    output: dict[str, int] = {}
    for key, value in candidates.items():
        if value is None or value == "":
            continue
        try:
            output[key] = int(value)
        except (TypeError, ValueError):
            continue
    return output


def validate_crawler_contract(scan: dict, review: dict) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if scan.get("success") is not True:
        errors.append(_issue("scan_not_successful", _str(scan.get("error") or "scanner returned success!=true")))

    pages = [item for item in (_list(scan.get("crawled_pages")) or _list(scan.get("pages"))) if isinstance(item, dict)]
    if not pages:
        errors.append(_issue("no_page_evidence", "The scan returned no crawled page evidence."))

    render = _dict(scan.get("render_evidence"))
    render_state = _str(render.get("evidence_state"))
    evaluated = _int(render.get("pages_evaluated"))
    if render_state == "raw_html_sufficient" and evaluated == 0:
        errors.append(_issue(
            "zero_page_raw_html_sufficient",
            "The scan labeled raw HTML sufficient despite zero evaluable HTML pages.",
        ))
    if render_state == "insufficient_raw_html_evidence":
        warnings.append(_issue(
            "insufficient_render_coverage",
            _str(_dict(render.get("coverage")).get("reason") or "Renderer evidence was inconclusive."),
        ))

    redirect_indexable = [
        _page_path(page)
        for page in pages
        if (
            _str(page.get("indexability_state")) == "Redirected"
            or bool(page.get("redirect_state"))
            or 300 <= _int(page.get("status_code")) < 400
        )
        and page.get("indexable") is True
    ]
    if redirect_indexable:
        errors.append(_issue(
            "redirect_marked_indexable",
            "Redirect source URLs were marked indexable: " + ", ".join(redirect_indexable[:5]),
            count=len(redirect_indexable),
        ))

    missing_states = [
        _page_path(page)
        for page in pages
        if not page.get("trust_discovery_probe") and not _str(page.get("indexability_state"))
    ]
    if missing_states:
        warnings.append(_issue(
            "missing_indexability_state",
            "Pages lacked an explicit indexability state: " + ", ".join(missing_states[:5]),
            count=len(missing_states),
        ))

    soft_404_paths = {
        _page_path(page)
        for page in pages
        if page.get("soft_404_suspected") or _str(page.get("indexability_state")) == "Soft 404"
    }
    raw_findings = [item for item in _list(scan.get("raw_findings")) if isinstance(item, dict)]
    soft_404_noise = [
        item
        for item in raw_findings
        if _finding_path(item) in soft_404_paths and _str(item.get("rule")) in METADATA_NOISE_RULES
    ]
    if soft_404_noise:
        errors.append(_issue(
            "soft_404_metadata_noise",
            "Confirmed soft-404 pages retained metadata/template noise findings.",
            count=len(soft_404_noise),
        ))

    review_findings = [
        item
        for item in (
            _list(review.get("cleaned_fixes"))
            or _list(review.get("fixes"))
            or _list(review.get("findings"))
        )
        if isinstance(item, dict)
    ]
    ids = [_str(item.get("fix_id") or item.get("id")) for item in review_findings]
    duplicate_ids = [key for key, count in Counter(key for key in ids if key).items() if count > 1]
    if duplicate_ids:
        errors.append(_issue(
            "duplicate_review_finding_ids",
            "Python Review returned duplicate finding IDs: " + ", ".join(duplicate_ids[:5]),
            count=len(duplicate_ids),
        ))

    missing_affected = [item for item in review_findings if not _list(item.get("affected_pages"))]
    if missing_affected:
        errors.append(_issue(
            "review_finding_missing_affected_pages",
            "Python Review findings lacked affected_pages evidence.",
            count=len(missing_affected),
        ))

    missing_sources = [item for item in review_findings if not _list(item.get("source_pages"))]
    if missing_sources:
        errors.append(_issue(
            "review_finding_missing_source_pages",
            "Python Review findings lacked source_pages evidence.",
            count=len(missing_sources),
        ))

    scores = _score_values(review)
    distinct_scores = sorted(set(scores.values()))
    if len(distinct_scores) > 1:
        errors.append(_issue(
            "review_score_mismatch",
            "Authoritative score fields disagreed: " + ", ".join(f"{key}={value}" for key, value in scores.items()),
        ))

    scan_status = _str(review.get("scan_status") or _dict(review.get("website_health_report")).get("scan_status"))
    provisional = bool(
        review.get("score_is_provisional")
        or _dict(review.get("website_health_report")).get("score_is_provisional")
    )
    if scan_status in {"blocked_or_incomplete", "incomplete_evidence", "complete_with_access_limitations"} and not provisional:
        errors.append(_issue(
            "access_limited_score_not_provisional",
            f"Review status {scan_status} was not marked provisional.",
        ))

    return {
        "version": CRAWLER_ACCEPTANCE_VERSION,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "error_codes": [item["code"] for item in errors],
        "warning_codes": [item["code"] for item in warnings],
    }


def _finding_summary(findings: Iterable[dict]) -> dict[str, int]:
    return dict(Counter(_str(item.get("rule") or "unknown") for item in findings if isinstance(item, dict)))


def _state_summary(pages: Iterable[dict]) -> dict[str, int]:
    return dict(Counter(_str(page.get("indexability_state") or "Unknown") for page in pages if isinstance(page, dict)))


def _compact_finding(finding: dict) -> dict[str, Any]:
    return {
        "id": _str(finding.get("fix_id") or finding.get("id")),
        "rule": _str(finding.get("rule")),
        "title": _str(finding.get("issue_title") or finding.get("title")),
        "priority": _str(finding.get("priority")),
        "page_scope": _str(finding.get("page_scope")),
        "affected_pages": _list(finding.get("affected_pages"))[:10],
        "source_pages": _list(finding.get("source_pages"))[:10],
        "evidence_status": _str(finding.get("evidence_status")),
    }


def build_acceptance_record(
    manifest_record: dict[str, Any],
    scan: dict[str, Any],
    review: dict[str, Any],
    *,
    duration_seconds: float,
) -> dict[str, Any]:
    pages = [item for item in (_list(scan.get("crawled_pages")) or _list(scan.get("pages"))) if isinstance(item, dict)]
    review_findings = [
        item
        for item in (
            _list(review.get("cleaned_fixes"))
            or _list(review.get("fixes"))
            or _list(review.get("findings"))
        )
        if isinstance(item, dict)
    ]
    render = _dict(scan.get("render_evidence"))
    validation = validate_crawler_contract(scan, review)
    score_values = _score_values(review)
    authoritative_score = score_values.get("health_score")
    if authoritative_score is None and score_values:
        authoritative_score = next(iter(score_values.values()))

    return {
        "version": CRAWLER_ACCEPTANCE_VERSION,
        "site": _str(manifest_record.get("site")),
        "url": _str(manifest_record.get("url")),
        "stratum": _str(manifest_record.get("stratum")),
        "scan_mode": _str(manifest_record.get("scan_mode") or "advanced"),
        "duration_seconds": round(max(0.0, float(duration_seconds or 0.0)), 2),
        "scanner_version": _str(scan.get("scanner_version") or scan.get("version")),
        "review_version": _str(review.get("review_version") or review.get("version")),
        "pages_crawled": _int(scan.get("pages_crawled")),
        "pages_found": _int(scan.get("pages_found")),
        "health_score": authoritative_score,
        "scan_status": _str(review.get("scan_status") or _dict(review.get("website_health_report")).get("scan_status")),
        "review_confidence_state": _str(review.get("review_confidence_state")),
        "score_is_provisional": bool(review.get("score_is_provisional")),
        "access_evidence_state": _str(review.get("access_evidence_state")),
        "render_evidence": {
            "state": _str(render.get("evidence_state")),
            "pages_evaluated": _int(render.get("pages_evaluated")),
            "suspected_pages": _int(render.get("client_rendering_suspected_pages")),
            "suspected_ratio": render.get("suspected_ratio"),
            "coverage": _dict(render.get("coverage")),
        },
        "indexability_states": _state_summary(pages),
        "finding_rules": _finding_summary(review_findings),
        "finding_count": len(review_findings),
        "top_findings": [_compact_finding(item) for item in review_findings[:12]],
        "validation": validation,
    }


def summarize_acceptance(
    manifest: list[dict[str, Any]],
    records: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_stratum[_str(record.get("stratum"))].append(record)

    requested_by_stratum = Counter(_str(item.get("stratum")) for item in manifest)
    completed_by_stratum = Counter(_str(item.get("stratum")) for item in records)
    passed_records = [record for record in records if _dict(record.get("validation")).get("passed")]

    violation_sites: dict[str, set[str]] = defaultdict(set)
    warning_sites: dict[str, set[str]] = defaultdict(set)
    finding_sites: dict[str, set[str]] = defaultdict(set)
    for record in records:
        site = _str(record.get("site"))
        validation = _dict(record.get("validation"))
        for code in _list(validation.get("error_codes")):
            violation_sites[_str(code)].add(site)
        for code in _list(validation.get("warning_codes")):
            warning_sites[_str(code)].add(site)
        for rule in _dict(record.get("finding_rules")):
            finding_sites[_str(rule)].add(site)

    recurring_violations = {
        code: sorted(sites)
        for code, sites in sorted(violation_sites.items())
        if len(sites) >= 2
    }
    recurring_warnings = {
        code: sorted(sites)
        for code, sites in sorted(warning_sites.items())
        if len(sites) >= 2
    }
    recurring_findings = {
        rule: sorted(sites)
        for rule, sites in sorted(finding_sites.items(), key=lambda item: (-len(item[1]), item[0]))
        if len(sites) >= 2
    }

    strata_complete = all(
        requested_by_stratum.get(stratum, 0) >= EXPECTED_SITES_PER_STRATUM
        and completed_by_stratum.get(stratum, 0) >= EXPECTED_SITES_PER_STRATUM
        for stratum in REQUIRED_STRATA
    )
    complete = len(records) == len(manifest) and not failures and strata_complete
    acceptance_passed = bool(complete and len(passed_records) == len(records) and not recurring_violations)

    return {
        "version": CRAWLER_ACCEPTANCE_VERSION,
        "requested_sites": len(manifest),
        "completed_sites": len(records),
        "failed_sites": len(failures),
        "contract_passed_sites": len(passed_records),
        "complete": complete,
        "acceptance_passed": acceptance_passed,
        "freeze_recommendation": "freeze_beta_crawler" if acceptance_passed else "patch_or_rerun",
        "requested_by_stratum": dict(requested_by_stratum),
        "completed_by_stratum": dict(completed_by_stratum),
        "recurring_contract_violations": recurring_violations,
        "recurring_warnings": recurring_warnings,
        "recurring_finding_rules": recurring_findings,
        "records": records,
        "failures": failures,
    }


def format_acceptance_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Final crawler validation",
        "",
        f"- Version: `{summary.get('version', CRAWLER_ACCEPTANCE_VERSION)}`",
        f"- Requested sites: {summary.get('requested_sites', 0)}",
        f"- Completed sites: {summary.get('completed_sites', 0)}",
        f"- Failed sites: {summary.get('failed_sites', 0)}",
        f"- Contract-passing sites: {summary.get('contract_passed_sites', 0)}",
        f"- Acceptance complete: {'yes' if summary.get('complete') else 'no'}",
        f"- Acceptance passed: {'yes' if summary.get('acceptance_passed') else 'no'}",
        f"- Recommendation: **{summary.get('freeze_recommendation', 'patch_or_rerun')}**",
        "",
        "| Site | Segment | Pages | Score | Status | Render evidence | Contract |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for record in summary.get("records", []):
        render = _dict(record.get("render_evidence"))
        validation = _dict(record.get("validation"))
        lines.append(
            "| {site} | {stratum} | {pages} | {score} | {status} | {render} ({evaluated}) | {contract} |".format(
                site=_str(record.get("site")),
                stratum=_str(record.get("stratum")),
                pages=_int(record.get("pages_crawled")),
                score=record.get("health_score") if record.get("health_score") is not None else "—",
                status=_str(record.get("scan_status")) or "—",
                render=_str(render.get("state")) or "—",
                evaluated=_int(render.get("pages_evaluated")),
                contract="pass" if validation.get("passed") else "fail",
            )
        )

    recurring = _dict(summary.get("recurring_contract_violations"))
    lines.extend(["", "## Recurring contract violations", ""])
    if recurring:
        for code, sites in recurring.items():
            lines.append(f"- `{code}`: {', '.join(sites)}")
    else:
        lines.append("- None detected across two or more sites.")

    warnings = _dict(summary.get("recurring_warnings"))
    lines.extend(["", "## Recurring warnings", ""])
    if warnings:
        for code, sites in warnings.items():
            lines.append(f"- `{code}`: {', '.join(sites)}")
    else:
        lines.append("- None detected across two or more sites.")

    findings = _dict(summary.get("recurring_finding_rules"))
    lines.extend(["", "## Repeated customer finding rules", ""])
    if findings:
        for rule, sites in list(findings.items())[:20]:
            lines.append(f"- `{rule}`: {len(sites)} sites — {', '.join(sites)}")
    else:
        lines.append("- No rule appeared on two or more sites.")

    if summary.get("failures"):
        lines.extend(["", "## Failed scans", ""])
        for failure in summary["failures"]:
            lines.append(f"- `{_str(failure.get('site'))}`: {_str(failure.get('error'))}")

    lines.append("")
    return "\n".join(lines)
