import json

from app.extract import extract_page
from app.stage2_local_entity_producer import (
    LOCAL_ENTITY_PRODUCER_VERSION,
    build_local_entity_scan_evidence,
)


def _html(entity):
    return (
        "<html><head><title>Location</title>"
        f"<script type='application/ld+json'>{json.dumps(entity)}</script>"
        "</head><body><main><h1>Location</h1><p>Visit this location.</p></main></body></html>"
    )


def _page(url, entity, *, status=200):
    return extract_page(
        _html(entity),
        url,
        url,
        status,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )


def test_b13_extracts_bounded_localbusiness_fields_and_explicit_identity_from_accepted_html():
    entity = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "@id": "https://example.com/locations/paris#store",
        "name": "Example Paris",
        "telephone": "+33 1 23 45 67 89",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "1 Rue Exemple",
            "addressLocality": "Paris",
            "postalCode": "75001",
            "addressCountry": "FR",
        },
        "openingHours": ["Mo-Fr 09:00-18:00"],
    }
    page = _page("https://example.com/locations/paris", entity)
    envelope = page["local_entity_observations"]

    assert envelope["version"] == LOCAL_ENTITY_PRODUCER_VERSION
    assert envelope["state"] == "observed"
    assert envelope["candidate_count"] == 1
    assert envelope["selected_count"] == 1
    observation = envelope["observations"][0]
    assert observation["accepted"] is True
    assert observation["applicable"] is True
    assert observation["entity_match"] == "verified"
    assert observation["entity_key"] == "https://example.com/locations/paris#store"
    assert observation["name"] == "Example Paris"
    assert observation["address"] == "1 Rue Exemple, Paris, 75001, FR"
    assert observation["phone"] == "+33 1 23 45 67 89"
    assert observation["regular_hours"] == "Mo-Fr 09:00-18:00"
    assert observation["regular_hours_applicable"] is True

    scan_evidence = build_local_entity_scan_evidence([page])
    assert scan_evidence["eligible_observations"] == 1
    assert scan_evidence["completeness"][0]["state"] == "pass"
    assert scan_evidence["completeness"][0]["missing_required"] == []
    assert scan_evidence["nap_consistency"]["state"] == "pass"


def test_b13_missing_hours_without_explicit_applicability_is_unknown_not_a_defect():
    entity = {
        "@context": "https://schema.org",
        "@type": "Store",
        "@id": "https://example.com/locations/soon#store",
        "name": "Future Store",
        "telephone": "+1 555 555 1212",
        "address": "10 Future Street",
    }
    evidence = build_local_entity_scan_evidence([_page("https://example.com/locations/soon", entity)])

    row = evidence["completeness"][0]
    assert row["state"] == "not_verified"
    assert row["missing_required"] == []
    assert row["unverified_fields"] == ["regular_hours"]


def test_b14_same_explicit_entity_id_can_prove_a_phone_inconsistency_across_pages():
    first = {
        "@context": "https://schema.org",
        "@type": "Store",
        "@id": "https://example.com/entities/store-1",
        "name": "Store One",
        "telephone": "+1 555 555 1212",
        "address": "1 Main Street",
        "openingHours": "Mo-Fr 09:00-17:00",
    }
    second = dict(first, telephone="+1 555 555 9999")
    evidence = build_local_entity_scan_evidence([
        _page("https://example.com/locations/store-1", first),
        _page("https://example.com/store-finder/store-1", second),
    ])

    assert evidence["nap_consistency"]["state"] == "fail"
    assert evidence["nap_consistency"]["verified_observations"] == 2
    assert evidence["nap_consistency"]["inconsistencies"] == [{
        "entity_key": "https://example.com/entities/store-1",
        "fields": ["phone"],
        "source_count": 2,
        "provenance": ["structured_data"],
    }]


def test_b14_matching_name_address_or_phone_without_explicit_id_never_proves_entity_identity():
    entity = {
        "@context": "https://schema.org",
        "@type": "Store",
        "name": "Store One",
        "telephone": "+1 555 555 1212",
        "address": "1 Main Street",
        "openingHours": "Mo-Fr 09:00-17:00",
    }
    evidence = build_local_entity_scan_evidence([
        _page("https://example.com/locations/store-1", entity),
        _page("https://example.com/store-finder/store-1", entity),
    ])

    assert evidence["nap_consistency"]["state"] == "not_verified"
    assert evidence["nap_consistency"]["verified_observations"] == 0
    assert evidence["nap_consistency"]["ambiguous_observations"] == 2
    assert evidence["nap_consistency"]["inconsistencies"] == []


def test_b13_rejects_structured_local_entity_claims_from_unusable_http_evidence():
    entity = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "@id": "https://example.com/entities/store-1",
        "name": "Store One",
        "telephone": "555",
        "address": "1 Main Street",
    }
    page = _page("https://example.com/blocked", entity, status=403)
    envelope = page["local_entity_observations"]

    assert envelope["state"] == "not_verified"
    assert envelope["candidate_count"] == 0
    assert envelope["observations"] == []


def test_b13_malformed_jsonld_stays_unknown_instead_of_becoming_no_local_entity():
    html = (
        "<html><head><title>Location</title>"
        "<script type='application/ld+json'>{not valid json</script>"
        "</head><body><main><h1>Location</h1></main></body></html>"
    )
    page = extract_page(
        html,
        "https://example.com/locations/a",
        "https://example.com/locations/a",
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )

    envelope = page["local_entity_observations"]
    assert envelope["state"] == "not_verified"
    assert envelope["reason"] == "local_entity_structured_data_malformed"
    assert envelope["malformed_script_count"] == 1
    assert envelope["observations"] == []
