import json
from pathlib import Path
from urllib.parse import urlparse

FIXTURE_DIR = Path(__file__).parent / "fixtures"
REQUIRED_TOP_LEVEL_FIELDS = {
    "scanner_version",
    "crawl_policy",
    "crawl_policy_source",
    "url_evidence_summary",
    "verified_failed_pages",
    "suspicious_url_artifacts",
    "pages",
    "grouped_findings",
}
REQUIRED_PAGE_FIELDS = {
    "url",
    "status_code",
    "estimated_page_intent",
    "page_template_family",
    "discovered_from",
    "source_pages",
}
DEVELOPER_RULE_IDS = {
    "blocked_page",
    "blocked_page_429",
    "broken_page",
    "canonical_missing",
    "canonical_to_other_domain",
    "canonical_to_other_url",
    "duplicate_route_casing",
    "free_base44_subdomain",
    "internal_route_indexable",
    "localbusiness_schema",
    "product_schema",
    "route_boundary_candidate_indexable",
    "schema",
    "structured_data",
}


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open() as handle:
        return json.load(handle)


def load_all_fixtures() -> dict[str, dict]:
    return {path.name: load_fixture(path.name) for path in sorted(FIXTURE_DIR.glob("*.scan.json"))}


def path_for(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or "/"


def duplicate_casing_paths(pages: list[dict]) -> set[str]:
    seen: dict[str, str] = {}
    duplicates: set[str] = set()

    for page in pages:
        path = path_for(page["url"])
        lower = path.lower()
        if lower in seen and seen[lower] != path:
            duplicates.add(lower)
        seen[lower] = path

    return duplicates


def test_required_advanced_scan_contract_fields_exist_for_every_fixture():
    for name, scan in load_all_fixtures().items():
        missing = REQUIRED_TOP_LEVEL_FIELDS - set(scan)
        assert not missing, f"{name} is missing top-level fields: {sorted(missing)}"


def test_every_crawled_page_exposes_template_intent_and_provenance():
    for name, scan in load_all_fixtures().items():
        for page in scan["pages"]:
            missing = REQUIRED_PAGE_FIELDS - set(page)
            assert not missing, f"{name} page {page.get('url')} is missing fields: {sorted(missing)}"
            assert page["page_template_family"], f"{name} page {page['url']} needs a template family"
            assert page["estimated_page_intent"], f"{name} page {page['url']} needs estimated intent"


def test_policy_failure_fails_open_and_does_not_claim_high_health():
    scan = load_fixture("saas-auth-app.scan.json")

    assert scan["crawl_policy_source"] == "failed"
    assert scan["pages_crawled"] > 1
    assert scan["health_score"] <= 70


def test_suspicious_encoded_urls_are_not_confirmed_broken_links():
    scan = load_fixture("meilleurtaux.scan.json")

    assert scan["suspicious_url_artifacts"]
    for artifact in scan["suspicious_url_artifacts"]:
        assert artifact["url_confidence"] == "crawler_artifact"
        assert artifact["confirmation_state"] != "confirmed_broken"
        assert artifact.get("source_pages", []) == []


def test_verified_404s_and_broken_findings_have_source_page_evidence():
    for name, scan in load_all_fixtures().items():
        for failed_page in scan["verified_failed_pages"]:
            assert failed_page.get("source_pages"), f"{name} verified failed page needs source evidence"

        for finding in scan["grouped_findings"]:
            if finding["rule_id"] in {"broken_page", "404_error", "410_error"}:
                evidence = finding.get("source_pages") or finding.get("evidence", {}).get("source_pages")
                assert evidence, f"{name} broken-page finding needs source evidence"


def test_blocked_or_429_pages_cannot_score_as_good():
    scan = load_fixture("meilleurtaux.scan.json")

    assert any(f["rule_id"] in {"blocked_page", "blocked_page_429"} for f in scan["grouped_findings"])
    assert scan["health_score"] <= 70


def test_route_boundary_candidates_are_crawled_and_flagged():
    for fixture_name in ["jacks-surfboards.scan.json", "saas-auth-app.scan.json"]:
        scan = load_fixture(fixture_name)
        route_pages = [page for page in scan["pages"] if page.get("route_boundary_candidate")]
        route_findings = [finding for finding in scan["grouped_findings"] if finding["rule_id"] == "route_boundary_candidate_indexable"]

        assert route_pages, f"{fixture_name} should crawl route-boundary candidates"
        assert route_findings, f"{fixture_name} should flag indexable route-boundary candidates"
        assert all(finding["owner"] == "Your web person" for finding in route_findings)


def test_duplicate_url_casing_is_flagged():
    scan = load_fixture("saas-auth-app.scan.json")

    assert "/dashboard" in duplicate_casing_paths(scan["pages"])
    assert any(finding["rule_id"] == "duplicate_route_casing" for finding in scan["grouped_findings"])


def test_developer_level_fixes_are_assigned_to_web_person():
    for name, scan in load_all_fixtures().items():
        for finding in scan["grouped_findings"]:
            if finding["rule_id"] in DEVELOPER_RULE_IDS:
                assert finding["owner"] == "Your web person", f"{name} {finding['rule_id']} should not be assigned to You"


def test_meilleurtaux_prioritizes_calculators_and_comparison_before_archives():
    scan = load_fixture("meilleurtaux.scan.json")
    first_twenty_intents = [page["estimated_page_intent"] for page in scan["pages"][:20]]

    assert "calculator" in first_twenty_intents
    assert "comparison" in first_twenty_intents
    assert "archive" not in first_twenty_intents[:6]


def test_funbooker_groups_repeated_listing_template_issues():
    scan = load_fixture("funbooker.scan.json")

    grouped_alt = [
        finding
        for finding in scan["grouped_findings"]
        if finding["rule_id"] == "image_alt_text"
        and finding.get("template_family") in {"listing_page", "category_page"}
    ]

    assert grouped_alt
    assert any(len(finding.get("urls", [])) >= 5 for finding in grouped_alt)


def test_shopify_groups_repeated_product_template_failures():
    scan = load_fixture("jacks-surfboards.scan.json")

    grouped_product_findings = [
        finding
        for finding in scan["grouped_findings"]
        if finding.get("template_family") == "product_page"
    ]

    assert grouped_product_findings
    assert any(len(finding.get("urls", [])) >= 3 for finding in grouped_product_findings)


def test_center_street_structural_findings_are_not_dropped():
    scan = load_fixture("center-street-lending.scan.json")
    rule_ids = {finding["rule_id"] for finding in scan["grouped_findings"]}

    assert rule_ids & {"localbusiness_schema", "schema", "trust_signal_gap", "broken_page", "cta_gap"}
