import json

from app.extract import extract_page
from app.stage2_local_entity_producer import build_local_entity_scan_evidence


def _page(url: str, entity: dict):
    html = (
        "<html><head><title>Location</title>"
        f"<script type='application/ld+json'>{json.dumps(entity)}</script>"
        "</head><body><main><h1>Location</h1></main></body></html>"
    )
    return extract_page(
        html,
        url,
        url,
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )


def _store(entity_id: str, phone: str = "+1 555 555 1212") -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Store",
        "@id": entity_id,
        "name": "Store One",
        "telephone": phone,
        "address": "1 Main Street",
        "openingHours": "Mo-Fr 09:00-17:00",
    }


def test_b14_relative_jsonld_ids_do_not_join_distinct_pages_without_base_resolution():
    first = _page("https://example.com/locations/a", _store("#store"))
    second = _page("https://example.com/locations/b", _store("#store", "+1 555 555 9999"))

    first_observation = first["local_entity_observations"]["observations"][0]
    assert first_observation["entity_key"] == "#store"
    assert first_observation["entity_match"] == "unverified"
    assert first_observation["entity_identity_reason"] == "relative_jsonld_id_requires_base_resolution"

    evidence = build_local_entity_scan_evidence([first, second])
    assert evidence["nap_consistency"]["state"] == "not_verified"
    assert evidence["nap_consistency"]["verified_observations"] == 0
    assert evidence["nap_consistency"]["ambiguous_observations"] == 2
    assert evidence["nap_consistency"]["comparable_entity_groups"] == 0
    assert evidence["nap_consistency"]["inconsistencies"] == []


def test_b14_absolute_http_jsonld_id_remains_verified_cross_page_identity():
    entity_id = "https://example.com/entities/store-1"
    first = _page("https://example.com/locations/a", _store(entity_id))
    second = _page("https://example.com/store-finder/a", _store(entity_id))

    observation = first["local_entity_observations"]["observations"][0]
    assert observation["entity_match"] == "verified"
    assert observation["entity_identity_reason"] == "absolute_http_jsonld_id"

    evidence = build_local_entity_scan_evidence([first, second])
    assert evidence["nap_consistency"]["state"] == "pass"
    assert evidence["nap_consistency"]["verified_observations"] == 2
    assert evidence["nap_consistency"]["comparable_entity_groups"] == 1
    assert evidence["nap_consistency"]["sitewide_consistency_claim"] is False
