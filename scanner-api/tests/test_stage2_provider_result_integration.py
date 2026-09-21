from app.extract import extract_page
from app.indexability_postprocess import apply_indexability_quality_to_result
from app.scan_job import build_authority_review_payload
from app.stage2_connected_provider_evidence import (
    CONNECTED_PROVIDER_EVIDENCE_VERSION,
    build_disconnected_provider_bundle,
)


DISCOVERY = {
    "discovered_from": ["seed"],
    "source_pages": [],
    "link_text_samples": [],
}


def _page(url: str = "https://example.com/") -> dict:
    return extract_page(
        "<html><head><title>Example</title></head><body><main><h1>Example</h1><p>Useful content.</p></main></body></html>",
        url,
        url,
        200,
        "text/html",
        DISCOVERY,
    )


def _result() -> dict:
    page = _page()
    return {
        "success": True,
        "website_url": "https://example.com/",
        "normalized_url": "https://example.com/",
        "pages": [page],
        "crawled_pages": [page],
        "pages_crawled": 1,
        "pages_found": 1,
        "raw_findings": [],
        "grouped_findings": [],
        "findings": [],
        "recommendations": [],
        "scan_summary": {},
        "technical_audit_summary": {},
    }


def test_disconnected_provider_bundle_is_explicit_and_contains_no_metrics_or_scan_claim():
    bundle = build_disconnected_provider_bundle(
        assessed_urls=["https://example.com/", "https://example.com/page?x=1"],
    )

    assert bundle["version"] == CONNECTED_PROVIDER_EVIDENCE_VERSION
    assert bundle["scan_identity_state"] == "unbound"
    assert bundle["provider_data_admitted"] is False
    assert bundle["crux"]["state"] == "disconnected"
    assert bundle["crux"]["scan_id"] is None
    assert bundle["crux"]["metrics"] is None
    assert bundle["gsc"]["state"] == "disconnected"
    assert bundle["gsc"]["scan_id"] is None
    assert bundle["gsc"]["assessed_url_count"] == 2
    assert bundle["gsc"]["pages"] == []
    assert bundle["gsc"]["coverage_complete_claim"] is False


def test_post_crawl_shared_result_records_provider_absence_without_creating_provider_findings():
    result = apply_indexability_quality_to_result(_result())

    bundle = result["connected_provider_evidence"]
    assert bundle["provider_data_admitted"] is False
    assert bundle["gsc"]["assessed_url_count"] == 1
    assert result["technical_audit_summary"]["connected_provider_evidence"] == bundle
    assert not any(
        str(item.get("rule") or "").startswith(("crux", "gsc"))
        for item in result["grouped_findings"]
    )


def test_disconnected_provider_state_survives_bounded_authority_review_payload():
    result = apply_indexability_quality_to_result(_result())
    result.update({
        "scan_id": "scan-provider-1",
        "scan_run_id": "scan-provider-1",
        "request_id": "req-provider-1",
        "idempotency_key": "req-provider-1",
        "scan_mode": "standard_150",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
    })

    authority = build_authority_review_payload(result)
    bundle = authority["technical_audit_summary"]["connected_provider_evidence"]

    assert bundle["version"] == CONNECTED_PROVIDER_EVIDENCE_VERSION
    assert bundle["provider_data_admitted"] is False
    assert bundle["crux"]["state"] == "disconnected"
    assert bundle["gsc"]["state"] == "disconnected"
    # The pre-authority disconnected envelope never borrows the later durable
    # scan id. Actual connected provider evidence must pass the exact-scan gate.
    assert bundle["crux"]["scan_id"] is None
    assert bundle["gsc"]["scan_id"] is None

def test_trust_discovery_probes_do_not_expand_provider_assessed_set_beyond_standard_150():
    pages = [_page(f"https://example.com/page-{index}") for index in range(150)]
    trust_probe = _page("https://example.com/privacy")
    trust_probe["trust_discovery_probe"] = True
    result = _result()
    result["pages"] = [*pages, trust_probe]
    result["crawled_pages"] = [*pages, trust_probe]
    result["pages_crawled"] = 151
    result["pages_found"] = 151

    processed = apply_indexability_quality_to_result(result)

    bundle = processed["connected_provider_evidence"]
    assert bundle["provider_data_admitted"] is False
    assert bundle["gsc"]["assessed_url_count"] == 150
