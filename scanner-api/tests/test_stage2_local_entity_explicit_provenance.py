import json

from app.extract import extract_page
from app.stage2_local_entity_producer import LOCAL_CONTEXT_PROVENANCE_VERSION, build_local_entity_scan_evidence


ORIGIN = "https://example.com"
ENTITY_ID = ORIGIN + "/entities/store-1"


def _entity(**extra):
    value = {
        "@context": "https://schema.org",
        "@type": "Store",
        "@id": ENTITY_ID,
        "name": "Store One",
        "telephone": "+1 555 555 1212",
        "address": "1 Main Street",
    }
    value.update(extra)
    return value


def _page(*, entity=None, heading="Store One", extra_html="", discovered_from=None):
    entity = entity or _entity()
    html = (
        "<html><head><title>Store One</title>"
        f"<script type='application/ld+json'>{json.dumps(entity)}</script>"
        "</head><body><main>"
        f"<h1>{heading}</h1>{extra_html}<p>Visit this location.</p>"
        "</main></body></html>"
    )
    return extract_page(
        html,
        ORIGIN + "/locations/store-1",
        ORIGIN + "/locations/store-1",
        200,
        "text/html",
        {
            "discovered_from": list(discovered_from or ["seed"]),
            "source_pages": [],
            "link_text_samples": [],
        },
    )


def test_b13_explicit_machine_status_makes_missing_hours_contextual_not_a_defect():
    page = _page(entity=_entity(businessStatus="https://schema.org/OpeningSoon"))
    observation = page["local_entity_observations"]["observations"][0]

    assert observation["context_provenance_version"] == LOCAL_CONTEXT_PROVENANCE_VERSION
    assert observation["contextual_status"] == "coming_soon"
    assert observation["contextual_status_state"] == "observed_explicit"
    assert observation["contextual_status_provenance"] == [{
        "source": "structured_data",
        "field": "businessStatus",
        "value": "https://schema.org/OpeningSoon",
    }]
    assert observation["regular_hours_applicable"] is False

    completeness = build_local_entity_scan_evidence([page])["completeness"][0]
    assert completeness["state"] == "pass"
    assert completeness["contextual_status"] == "coming_soon"
    assert completeness["missing_required"] == []
    assert completeness["unverified_fields"] == []


def test_b13_accepted_heading_can_supply_conservative_coming_soon_context():
    page = _page(heading="Store One — Coming Soon")
    observation = page["local_entity_observations"]["observations"][0]

    assert observation["contextual_status"] == "coming_soon"
    assert observation["contextual_status_state"] == "observed_context"
    assert observation["contextual_status_provenance"] == [{
        "source": "accepted_heading",
        "field": "h1",
        "value": "Store One — Coming Soon",
    }]
    assert observation["regular_hours_applicable"] is False


def test_b13_incidental_body_closed_word_does_not_invent_location_status():
    page = _page(extra_html="<p>Customer support is closed Sundays.</p>")
    observation = page["local_entity_observations"]["observations"][0]

    assert observation["contextual_status"] is None
    assert observation["contextual_status_state"] == "not_verified"
    assert observation["contextual_status_provenance"] == []
    assert observation["regular_hours_applicable"] is None


def test_b14_surface_provenance_records_sitemap_and_explicit_form_reference_without_changing_identity():
    page = _page(
        discovered_from=["sitemap", "internal_link"],
        extra_html=(
            "<form id='location-picker'>"
            f"<input type='hidden' name='store_id' value='{ENTITY_ID}'>"
            "</form>"
        ),
    )
    observation = page["local_entity_observations"]["observations"][0]

    assert observation["entity_match"] == "verified"
    assert observation["entity_key"] == ENTITY_ID
    assert observation["surface_provenance"] == [
        "structured_data",
        "sitemap_reference",
        "form_explicit_entity_id",
    ]


def test_b14_store_finder_marker_requires_exact_explicit_entity_id():
    matching = _page(
        extra_html=(
            f"<div data-store-finder='true' data-entity-id='{ENTITY_ID}'></div>"
        ),
    )["local_entity_observations"]["observations"][0]
    mismatched = _page(
        extra_html=(
            "<div data-store-finder='true' data-entity-id='https://example.com/entities/store-2'></div>"
        ),
    )["local_entity_observations"]["observations"][0]

    assert "store_finder_explicit_entity_id" in matching["surface_provenance"]
    assert "store_finder_explicit_entity_id" not in mismatched["surface_provenance"]
    assert mismatched["entity_match"] == "verified"
    assert mismatched["entity_key"] == ENTITY_ID


def test_b14_form_or_sitemap_context_never_promotes_missing_structured_identity():
    no_id = _entity()
    no_id.pop("@id")
    page = _page(
        entity=no_id,
        discovered_from=["sitemap"],
        extra_html=(
            f"<form><input type='hidden' name='store_id' value='{ENTITY_ID}'></form>"
        ),
    )
    observation = page["local_entity_observations"]["observations"][0]

    assert observation["entity_match"] == "unverified"
    assert observation["entity_key"] == ""
    assert observation["surface_provenance"] == ["structured_data", "sitemap_reference"]
    nap = build_local_entity_scan_evidence([page])["nap_consistency"]
    assert nap["state"] == "not_verified"
    assert nap["verified_observations"] == 0
    assert nap["sitewide_consistency_claim"] is False
