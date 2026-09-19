from datetime import date

from app.stage2_coverage_evidence import (
    CRUX_ADAPTER_VERSION,
    GSC_ADAPTER_VERSION,
    MAIN_TEXT_EVIDENCE_VERSION,
    assess_contextual_freshness,
    assess_local_entity_completeness,
    assess_nap_consistency,
    compare_raw_rendered_hub_links,
    money_page_reachability,
    near_duplicate_main_content,
    optional_crux_adapter,
    optional_gsc_adapter,
    page_weight_evidence,
)


def _page(url, text, **extra):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "main_text_evidence_version": MAIN_TEXT_EVIDENCE_VERSION,
        "main_text_verified": True,
        "main_text": text,
        **extra,
    }


def test_near_duplicates_use_verified_main_text_not_template_chrome():
    # Use high-entropy substantive text so the shingle similarity measures the
    # intended near-duplicate relationship rather than a tiny repeating token
    # cycle whose deduplicated shingles would understate similarity.
    common = " ".join(f"token{index}" for index in range(100))
    pages = [
        _page("https://example.com/a", common + " alpha"),
        _page("https://example.com/b", common + " beta"),
        _page("https://example.com/c", " ".join(f"unique{index}" for index in range(100))),
        {**_page("https://example.com/unverified", common), "main_text_verified": False},
    ]
    evidence = near_duplicate_main_content(pages)
    assert evidence["state"] == "pass"
    assert evidence["eligible_pages"] == 3
    assert len(evidence["clusters"]) == 1
    assert set(evidence["clusters"][0]["affected_pages"]) == {
        "https://example.com/a",
        "https://example.com/b",
    }


def test_near_duplicates_stay_unknown_without_verified_main_text():
    evidence = near_duplicate_main_content(
        [{"url": "https://example.com/a", "status_code": 200, "page_evidence_class": "usable_html"}]
    )
    assert evidence["state"] == "not_verified"
    assert evidence["clusters"] == []


def test_money_page_reachability_is_sample_scoped_not_sitewide_orphaning():
    evidence = money_page_reachability(
        [
            _page(
                "https://example.com/pricing",
                "x " * 50,
                page_template_family="pricing_page",
                source_pages=[],
                crawl_depth=5,
            ),
            _page(
                "https://example.com/product",
                "x " * 50,
                page_template_family="product_page",
                source_pages=["https://example.com/category"],
                crawl_depth=2,
                navigation_presence=True,
            ),
        ]
    )
    assert evidence["scope"] == "observed_standard150_sample_only"
    assert evidence["money_pages_observed"] == 2
    assert evidence["weak_routes"] == 1
    assert evidence["pages"][0]["reason"] == "weak_route_in_observed_sample"


def test_hub_comparison_discloses_selected_completed_failed_and_unassessed():
    pairs = [
        {
            "hub_url": f"https://example.com/h{index}",
            "raw_success": True,
            "rendered_success": True,
            "raw_links": ["/a"],
            "rendered_links": ["/a", f"/js{index}"],
        }
        for index in range(5)
    ] + [
        {
            "hub_url": "https://example.com/h5",
            "raw_success": True,
            "rendered_success": False,
            "raw_links": ["/a"],
            "rendered_links": [],
        }
    ]
    evidence = compare_raw_rendered_hub_links(pairs)
    assert evidence["selected"] == 5
    assert evidence["completed"] == 5
    assert evidence["failed"] == 0
    assert evidence["unassessed"] == 1
    assert evidence["hubs"][0]["render_only_count"] == 1


def test_failed_hub_render_does_not_claim_missing_links():
    evidence = compare_raw_rendered_hub_links(
        [
            {
                "hub_url": "https://example.com/hub",
                "raw_success": True,
                "rendered_success": False,
                "raw_links": ["/a"],
                "rendered_links": [],
            }
        ]
    )
    row = evidence["hubs"][0]
    assert row["state"] == "not_verified"
    assert row["raw_link_count"] is None
    assert row["rendered_link_count"] is None


def test_local_entity_requires_core_fields_but_optional_fields_are_not_defects():
    evidence = assess_local_entity_completeness(
        {
            "applicable": True,
            "accepted": True,
            "name": "Store A",
            "address": "1 Main St",
            "phone": "+1 555 555 1212",
            "regular_hours": "Mon-Fri 9-5",
        }
    )
    assert evidence["state"] == "pass"
    assert evidence["missing_required"] == []
    assert evidence["optional_available"]["holiday_hours"] is False
    assert evidence["optional_available"]["photos"] is False


def test_local_entity_unknown_or_nonapplicable_stays_nondefect():
    assert assess_local_entity_completeness({"applicable": None})["state"] == "not_verified"
    assert assess_local_entity_completeness({"applicable": False})["state"] == "not_applicable"


def test_nap_consistency_only_compares_verified_entity_matches():
    evidence = assess_nap_consistency(
        [
            {
                "accepted": True,
                "entity_key": "store-1",
                "entity_match": "verified",
                "name": "Store A",
                "address": "1 Main Street",
                "phone": "(555) 555-1212",
                "source": "location_page",
            },
            {
                "accepted": True,
                "entity_key": "store-1",
                "entity_match": "verified",
                "name": "Store A",
                "address": "99 Other Road",
                "phone": "555-555-1212",
                "source": "structured_data",
            },
            {
                "accepted": True,
                "entity_key": "store-1",
                "entity_match": "ambiguous",
                "name": "Other",
                "address": "Elsewhere",
                "phone": "000",
                "source": "form",
            },
        ]
    )
    assert evidence["state"] == "fail"
    assert evidence["ambiguous_observations"] == 1
    assert evidence["inconsistencies"][0]["fields"] == ["address"]


def test_nap_ambiguous_only_is_unknown_not_failure():
    evidence = assess_nap_consistency(
        [
            {
                "accepted": True,
                "entity_key": "maybe",
                "entity_match": "ambiguous",
                "name": "A",
                "address": "1 Main",
                "phone": "555",
                "source": "finder",
            }
        ]
    )
    assert evidence["state"] == "not_verified"
    assert evidence["inconsistencies"] == []


def test_freshness_requires_current_intent_and_current_scope_temporal_evidence():
    archived = assess_contextual_freshness(
        {"temporal_evidence": [{"date": "2022-01-01", "scope": "historical"}]},
        as_of=date(2026, 9, 19),
    )
    assert archived["state"] == "not_applicable"

    current = assess_contextual_freshness(
        {
            "current_content_intent": "current_rates",
            "current_content_intent_evidence": ["title: Current mortgage rates"],
            "temporal_evidence": [{"date": "2023-01-01", "scope": "current"}],
        },
        as_of=date(2026, 9, 19),
    )
    assert current["state"] == "fail"
    assert current["reason"] == "current_intent_conflicts_with_old_temporal_evidence"


def test_page_weight_keeps_unknown_wire_length_distinct_from_zero():
    evidence = page_weight_evidence(
        decoded_bytes=1200,
        inline_script_bytes=0,
        inline_style_bytes=150,
        transfer_bytes=0,
        transfer_measured=False,
    )
    assert evidence["transfer_bytes"] is None
    assert evidence["transfer_bytes_state"] == "unknown"
    assert evidence["decoded_bytes"] == 1200
    assert evidence["inline_script_bytes"] == 0


def test_crux_adapter_labels_disconnected_stale_and_connected_states():
    disconnected = optional_crux_adapter(connection_state="disconnected")
    assert disconnected["version"] == CRUX_ADAPTER_VERSION
    assert disconnected["metrics"] is None

    stale = optional_crux_adapter(
        connection_state="connected",
        observed_at=date(2026, 7, 1),
        as_of=date(2026, 9, 19),
        scope="url",
        metrics={"lcp_ms": 2100},
    )
    assert stale["state"] == "stale"
    assert stale["metrics"] is None

    connected = optional_crux_adapter(
        connection_state="connected",
        observed_at=date(2026, 9, 1),
        as_of=date(2026, 9, 19),
        scope="origin",
        metrics={"lcp_ms": 2100, "inp_ms": 180, "cls": 0.08},
    )
    assert connected["state"] == "connected"
    assert connected["scope"] == "origin"
    assert connected["metrics"]["lcp_ms"] == 2100


def test_gsc_adapter_never_fabricates_metrics_when_disconnected_or_stale():
    disconnected = optional_gsc_adapter(
        connection_state="disconnected", as_of=date(2026, 9, 19)
    )
    assert disconnected["version"] == GSC_ADAPTER_VERSION
    assert disconnected["metrics"] is None

    stale = optional_gsc_adapter(
        connection_state="connected",
        as_of=date(2026, 9, 19),
        observed_at=date(2026, 8, 1),
        metrics={"clicks": 20, "impressions": 200, "position": 4.5, "index_state": "indexed"},
    )
    assert stale["state"] == "stale"
    assert stale["metrics"] is None


def test_gsc_connected_metrics_are_bounded_and_explicit():
    connected = optional_gsc_adapter(
        connection_state="connected",
        as_of=date(2026, 9, 19),
        observed_at=date(2026, 9, 18),
        metrics={
            "clicks": 20,
            "impressions": 200,
            "position": 4.5,
            "index_state": "indexed",
            "query": "not retained",
        },
    )
    assert connected["state"] == "connected"
    assert connected["metrics"] == {
        "clicks": 20,
        "impressions": 200,
        "position": 4.5,
        "index_state": "indexed",
    }
