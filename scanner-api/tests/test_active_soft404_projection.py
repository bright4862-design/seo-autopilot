"""B07 active soft-404 evidence through the downstream customer contract."""

import json
from pathlib import Path
import subprocess

from app import scanner
from app.coverage_probes import (
    SOFT_404_PROBE_VERSION,
    build_soft_404_baseline_record,
    soft_404_signature_tokens,
)
from app.extract import extract_page
from app.indexability_postprocess import apply_indexability_quality_to_result
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.scan_job import build_local_review


ORIGIN = "https://example.com"
CURRENT = {
    "identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    "scan_origin": ORIGIN,
}


def _accepted_page(url: str, *, title: str, h1: str, description: str, word_count: int = 180) -> dict:
    html = (
        "<html><head>"
        f"<title>{title}</title>"
        f'<meta name="description" content="{description}">'
        "</head><body>"
        f"<h1>{h1}</h1><p>Catalog information remains intentionally bounded for this fixture.</p>"
        "</body></html>"
    )
    page = extract_page(
        html,
        url,
        url,
        200,
        "text/html",
        {"discovered_from": ["internal_link"], "source_pages": ["/catalog"], "link_text_samples": ["Missing offer"]},
    )
    # Keep the regression about active evidence, not the extractor's text-volume
    # heuristics. This word count deliberately prevents the legacy one-field
    # passive soft-404 heuristic from becoming high confidence by itself.
    page["word_count"] = word_count
    page["page_evidence_class"] = "usable_html"
    page["raw_html_truncated"] = False
    page["page_template_family"] = "activity_detail"
    return page


def _active_baseline() -> dict:
    probe_url = ORIGIN + "/catalog/__fixlist-missing-deadbeef1234"
    probe_page = _accepted_page(
        probe_url,
        title="Page not found",
        h1="Catalog entry",
        description="This catalog entry is no longer available",
    )
    record = build_soft_404_baseline_record(
        probe_page,
        probe_url,
        {"synthetic": True, "probe_kind": "path_family", "page_family": "activity_detail"},
    )
    record["signature_tokens"] = soft_404_signature_tokens(probe_page)
    assert record["state"] == "fail"
    assert record["reason"] == "http_200_missing_intent_baseline"
    return record


def _scan(page: dict, baselines: list[dict]) -> dict:
    raw = scanner.build_findings([page], **CURRENT)
    return {
        "success": True,
        "website_url": ORIGIN,
        "crawl_scope": {"requested_origin": ORIGIN},
        "pages": [page],
        "crawled_pages": [page],
        "pages_found": 1,
        "pages_crawled": 1,
        "raw_findings": raw,
        "findings": scanner.group_findings(raw),
        "coverage_probe_evidence": {
            "version": "coverage_probe_scheduler_v1_shared_request_budget",
            "soft_404_baselines": baselines,
        },
    }


def _assert_persisted_customer_output(result: dict, rule: str, urls: list[str]) -> None:
    completed = subprocess.run(
        ["node", "tests/helpers/assertPublishedEvidenceOutput.mjs"],
        input=json.dumps({
            "scan": result,
            "review": build_local_review(result),
            "expectedUrls": urls,
            "expectedRule": rule,
            "expectedEligible": 0,
        }),
        text=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2],
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def test_active_baseline_match_becomes_authenticated_soft404_without_expanding_assessed_pages():
    url = ORIGIN + "/catalog/missing-offer"
    page = _accepted_page(
        url,
        title="Page not found",
        h1="Catalog entry",
        description="This catalog entry is no longer available",
    )
    result = apply_indexability_quality_to_result(
        _scan(page, [_active_baseline()]),
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    assert result["pages_crawled"] == 1
    assert len(result["pages"]) == 1
    assert result["pages"][0]["url"] == url
    assert result["pages"][0]["soft_404_suspected"] is True
    assert "active_baseline_match" in result["pages"][0]["soft_404_signals"]

    [finding] = [row for row in result["raw_findings"] if row["rule"] == "soft_404"]
    assert finding["affected_pages"] == [url]
    assert finding["evidence_status"] == "confirmed_active_baseline"
    assert finding["verification_state"] == "verified"
    assert finding["confidence_score"] == 98
    assert finding["observed_evidence_version"] == SOFT_404_PROBE_VERSION
    assert finding["verified_observed_pages"] == [url]

    [repair] = [row for row in build_local_review(result)["canonical_repairs"] if row["rule"] == "soft_404"]
    assert repair["affected_pages"] == [url]
    assert repair["observed_evidence_version"] == SOFT_404_PROBE_VERSION
    assert repair["verified_observed_pages"] == [url]
    _assert_persisted_customer_output(result, "soft_404", [url])


def test_grouped_active_soft404_keeps_exact_verified_page_union():
    urls = [
        ORIGIN + "/catalog/missing-offer-a",
        ORIGIN + "/catalog/missing-offer-b",
        ORIGIN + "/catalog/missing-offer-c",
    ]
    pages = [
        _accepted_page(
            url,
            title="Page not found",
            h1="Catalog entry",
            description="This catalog entry is no longer available",
        )
        for url in urls
    ]
    raw = scanner.build_findings(pages, **CURRENT)
    result = apply_indexability_quality_to_result(
        {
            "success": True,
            "website_url": ORIGIN,
            "crawl_scope": {"requested_origin": ORIGIN},
            "pages": pages,
            "crawled_pages": pages,
            "pages_found": len(pages),
            "pages_crawled": len(pages),
            "raw_findings": raw,
            "findings": scanner.group_findings(raw),
            "coverage_probe_evidence": {
                "version": "coverage_probe_scheduler_v1_shared_request_budget",
                "soft_404_baselines": [_active_baseline()],
            },
        },
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    [finding] = [row for row in result["findings"] if row["rule"] == "soft_404"]
    assert set(finding["affected_pages"]) == set(urls)
    assert finding["page_count"] == 3
    assert finding["observed_evidence_version"] == SOFT_404_PROBE_VERSION
    assert set(finding["verified_observed_pages"]) == set(urls)

    [repair] = [row for row in build_local_review(result)["canonical_repairs"] if row["rule"] == "soft_404"]
    assert set(repair["affected_pages"]) == set(urls)
    assert repair["observed_evidence_version"] == SOFT_404_PROBE_VERSION
    assert set(repair["verified_observed_pages"]) == set(urls)
    _assert_persisted_customer_output(result, "soft_404", urls)


def test_challenged_active_baseline_stays_unknown_and_does_not_invent_soft404():
    url = ORIGIN + "/catalog/healthy-offer"
    page = _accepted_page(
        url,
        title="Page not found",
        h1="Catalog entry",
        description="This catalog entry is no longer available",
    )
    challenged_probe = _accepted_page(
        ORIGIN + "/catalog/__fixlist-missing-blocked1234",
        title="Page not found",
        h1="Catalog entry",
        description="This catalog entry is no longer available",
    )
    challenged_probe["access_block_kind"] = "challenge"
    baseline = build_soft_404_baseline_record(
        challenged_probe,
        challenged_probe["url"],
        {"synthetic": True, "probe_kind": "path_family", "page_family": "activity_detail"},
    )
    baseline["signature_tokens"] = soft_404_signature_tokens(challenged_probe)
    assert baseline["state"] == "not_verified"

    result = apply_indexability_quality_to_result(
        _scan(page, [baseline]),
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    assert result["pages_crawled"] == 1
    assert result["pages"][0]["soft_404_suspected"] is False
    assert not [row for row in result["raw_findings"] if row["rule"] == "soft_404"]


def test_absent_active_baseline_preserves_legacy_passive_soft404_behavior():
    url = ORIGIN + "/legacy-missing"
    page = _accepted_page(
        url,
        title="Page not found",
        h1="Page not found",
        description="Missing page",
        word_count=40,
    )
    result = apply_indexability_quality_to_result(
        _scan(page, []),
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    [finding] = [row for row in result["raw_findings"] if row["rule"] == "soft_404"]
    assert finding["evidence_status"] == "confirmed_by_high_confidence_heuristic"
    assert "observed_evidence_version" not in finding
    assert "verified_observed_pages" not in finding
