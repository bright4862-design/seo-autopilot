import json

from app.extract import extract_page
from app.indexability_postprocess import apply_indexability_quality_to_result
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.scan_job import build_authority_review_payload
from app.stage2_local_entity_producer import LOCAL_ENTITY_PRODUCER_VERSION


ORIGIN = "https://example.com"


def _page(url: str, entity: dict) -> dict:
    html = (
        "<html><head><title>Location</title>"
        f"<script type='application/ld+json'>{json.dumps(entity)}</script>"
        "</head><body><main><h1>Location</h1><p>Visit this location.</p></main></body></html>"
    )
    return extract_page(
        html,
        url,
        url,
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )


def _result(pages: list[dict]) -> dict:
    return {
        "success": True,
        "website_url": ORIGIN,
        "crawl_scope": {"requested_origin": ORIGIN},
        "pages": pages,
        "crawled_pages": pages,
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "raw_findings": [],
        "findings": [],
        "grouped_findings": [],
        "technical_audit_summary": {},
    }


def _store(*, phone: str, entity_id: str = "https://example.com/entities/store-1") -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Store",
        "@id": entity_id,
        "name": "Store One",
        "telephone": phone,
        "address": "1 Main Street",
        "openingHours": "Mo-Fr 09:00-17:00",
    }


def test_b13_b14_aggregate_reaches_shared_result_and_signed_review_payload_without_new_repairs():
    pages = [
        _page(ORIGIN + "/locations/store-1", _store(phone="+1 555 555 1212")),
        _page(ORIGIN + "/store-finder/store-1", _store(phone="+1 555 555 1212")),
    ]
    updated = apply_indexability_quality_to_result(
        _result(pages),
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    evidence = updated["local_entity_scan_evidence"]
    assert evidence["producer_version"] == LOCAL_ENTITY_PRODUCER_VERSION
    assert evidence["eligible_observations"] == 2
    assert evidence["selected_observations"] == 2
    assert evidence["selection_truncated"] is False
    assert evidence["nap_consistency"]["state"] == "pass"
    assert evidence["nap_consistency"]["comparable_entity_groups"] == 1
    assert evidence["nap_consistency"]["sitewide_consistency_claim"] is False

    assert updated["technical_audit_summary"]["local_entity_scan_evidence"] == evidence
    assert updated["pages_crawled"] == 2
    assert len(updated["pages"]) == 2

    signed_review_payload = build_authority_review_payload(updated)
    signed_evidence = signed_review_payload["technical_audit_summary"]["local_entity_scan_evidence"]
    assert signed_evidence["producer_version"] == LOCAL_ENTITY_PRODUCER_VERSION
    assert signed_evidence["eligible_observations"] == 2
    assert signed_evidence["selected_observations"] == 2
    assert signed_evidence["selection_truncated"] is False
    assert signed_evidence["nap_consistency"]["state"] == "pass"
    assert signed_evidence["nap_consistency"]["comparable_entity_groups"] == 1
    assert signed_evidence["nap_consistency"]["sitewide_consistency_claim"] is False
    assert len(signed_evidence["completeness"]) == 2
    assert all(row["state"] == "pass" for row in signed_evidence["completeness"])
    assert all(row["entity_match"] == "verified" for row in signed_evidence["completeness"])

    serialized_signed = json.dumps(signed_evidence, sort_keys=True)
    assert "https://example.com/entities/store-1" not in serialized_signed
    assert ORIGIN + "/locations/store-1" not in serialized_signed
    assert ORIGIN + "/store-finder/store-1" not in serialized_signed
    for private_field in ("entity_key", "page_url", "contextual_status_provenance"):
        assert f'"{private_field}"' not in serialized_signed

    assert not [
        row
        for row in updated["findings"]
        if str(row.get("rule") or "").startswith(("local_entity", "nap_"))
    ]


def test_b14_verified_cross_page_nap_conflict_is_authenticated_evidence_but_not_promoted_to_customer_repair():
    pages = [
        _page(ORIGIN + "/locations/store-1", _store(phone="+1 555 555 1212")),
        _page(ORIGIN + "/store-finder/store-1", _store(phone="+1 555 555 9999")),
    ]
    updated = apply_indexability_quality_to_result(
        _result(pages),
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    evidence = updated["local_entity_scan_evidence"]
    nap = evidence["nap_consistency"]
    assert nap["state"] == "fail"
    assert nap["verified_observations"] == 2
    assert nap["comparable_entity_groups"] == 1
    assert nap["inconsistencies"] == [{
        "entity_key": "https://example.com/entities/store-1",
        "fields": ["phone"],
        "source_count": 2,
        "provenance": ["structured_data"],
    }]

    signed_review_payload = build_authority_review_payload(updated)
    signed_nap = signed_review_payload["technical_audit_summary"]["local_entity_scan_evidence"]["nap_consistency"]
    assert signed_nap["state"] == "fail"
    assert signed_nap["verified_observations"] == 2
    assert signed_nap["comparable_entity_groups"] == 1
    assert signed_nap["sitewide_consistency_claim"] is False
    assert signed_nap["inconsistencies"] == [{
        "fields": ["phone"],
        "source_count": 2,
        "provenance": ["structured_data"],
    }]
    assert "entity_key" not in signed_nap["inconsistencies"][0]
    assert not [
        row
        for row in updated["findings"]
        if str(row.get("rule") or "").startswith(("local_entity", "nap_"))
    ]


def test_b14_relative_entity_ids_remain_unverified_after_shared_result_attachment():
    pages = [
        _page(ORIGIN + "/locations/store-1", _store(phone="+1 555 555 1212", entity_id="#store")),
        _page(ORIGIN + "/store-finder/store-1", _store(phone="+1 555 555 1212", entity_id="#store")),
    ]
    updated = apply_indexability_quality_to_result(
        _result(pages),
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    )

    nap = updated["local_entity_scan_evidence"]["nap_consistency"]
    assert nap["state"] == "not_verified"
    assert nap["verified_observations"] == 0
    assert nap["ambiguous_observations"] == 2
    assert nap["comparable_entity_groups"] == 0
    assert nap["sitewide_consistency_claim"] is False
