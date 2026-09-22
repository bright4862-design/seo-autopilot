from copy import deepcopy

from app.nextgen_browser_performance_crux_provenance import (
    CRUX_BOUND_ADAPTER_VERSION,
    normalize_crux_query_record_evidence_bound,
    validate_bound_crux_contract,
)


def crux_url_payload():
    return {
        "record": {
            "key": {"url": "https://Example.COM/page#frag"},
            "metrics": {
                "largest_contentful_paint": {
                    "percentiles": {"p75": 2450},
                    "category": "FAST",
                }
            },
            "collectionPeriod": {
                "firstDate": {"year": 2026, "month": 8, "day": 20},
                "lastDate": {"year": 2026, "month": 9, "day": 16},
            },
        }
    }


def test_bound_crux_url_preserves_provider_identity_and_coverage():
    evidence = normalize_crux_query_record_evidence_bound(
        crux_url_payload(),
        observed_at="2026-09-21",
        scope="url",
        source_url="https://example.com/page",
    )
    assert evidence["state"] == "connected"
    assert evidence["adapter_version"] == CRUX_BOUND_ADAPTER_VERSION
    assert evidence["source_url"] == "https://example.com/page"
    assert evidence["coverage_period"] == {
        "first_date": "2026-08-20",
        "last_date": "2026-09-16",
    }
    assert evidence["provenance"]["record_source_url"] == "https://example.com/page"
    assert validate_bound_crux_contract(evidence)["valid"] is True


def test_bound_crux_origin_requires_true_origin_and_supports_origin_scope():
    payload = crux_url_payload()
    payload["record"]["key"] = {"origin": "https://Example.COM"}
    evidence = normalize_crux_query_record_evidence_bound(
        payload,
        scope="origin",
        source_url="https://example.com/",
    )
    assert evidence["state"] == "connected"
    assert evidence["source_url"] == "https://example.com/"
    assert validate_bound_crux_contract(evidence)["valid"] is True


def test_bound_crux_rejects_both_record_keys_even_when_one_is_invalid():
    payload = crux_url_payload()
    payload["record"]["key"] = {
        "url": "not-a-url",
        "origin": "https://e.test",
    }
    evidence = normalize_crux_query_record_evidence_bound(payload)
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_record_key_invalid"
    assert evidence["metrics"] is None


def test_bound_crux_rejects_page_shaped_origin_and_query_origin():
    for origin in ("https://e.test/path", "https://e.test/?q=1"):
        payload = crux_url_payload()
        payload["record"]["key"] = {"origin": origin}
        evidence = normalize_crux_query_record_evidence_bound(payload)
        assert evidence["state"] == "unavailable"
        assert evidence["reason"] == "crux_record_origin_identity_invalid"


def test_bound_crux_rejects_missing_or_reversed_collection_period():
    payload = crux_url_payload()
    payload["record"].pop("collectionPeriod")
    missing = normalize_crux_query_record_evidence_bound(payload)
    assert missing["state"] == "unavailable"
    assert missing["reason"] == "crux_collection_period_invalid"
    assert missing["coverage_period"] is None

    payload = crux_url_payload()
    payload["record"]["collectionPeriod"] = {
        "firstDate": {"year": 2026, "month": 9, "day": 17},
        "lastDate": {"year": 2026, "month": 9, "day": 16},
    }
    reversed_period = normalize_crux_query_record_evidence_bound(payload)
    assert reversed_period["state"] == "unavailable"
    assert reversed_period["reason"] == "crux_collection_period_invalid"


def test_bound_crux_rejects_embedded_credentials_in_record_url():
    payload = crux_url_payload()
    payload["record"]["key"] = {"url": "https://user:pass@e.test/a"}
    evidence = normalize_crux_query_record_evidence_bound(payload)
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_record_url_identity_invalid"


def test_bound_crux_rejects_page_url_as_origin_scoped_caller_identity():
    payload = crux_url_payload()
    payload["record"]["key"] = {"origin": "https://e.test"}
    evidence = normalize_crux_query_record_evidence_bound(
        payload,
        scope="origin",
        source_url="https://e.test/path",
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "crux_source_origin_identity_invalid"


def test_bound_crux_preserves_non_connected_state_without_measurements_or_coverage():
    evidence = normalize_crux_query_record_evidence_bound(
        crux_url_payload(),
        state="rate_limited",
    )
    assert evidence["state"] == "rate_limited"
    assert evidence["metrics"] is None
    assert evidence["coverage_period"] is None
    assert validate_bound_crux_contract(evidence)["valid"] is True


def test_bound_crux_integrity_rejects_tampered_source_and_coverage_provenance():
    evidence = normalize_crux_query_record_evidence_bound(
        crux_url_payload(),
        scope="url",
        source_url="https://example.com/page",
    )
    evidence["provenance"]["record_source_url"] = "https://example.com/other"
    evidence["provenance"]["coverage_period"] = {
        "first_date": "2026-08-20",
        "last_date": "2026-09-15",
    }
    result = validate_bound_crux_contract(evidence)
    assert result["valid"] is False
    assert "connected_source_identity_mismatch" in result["reasons"]
    assert "connected_coverage_period_mismatch" in result["reasons"]


def test_bound_crux_does_not_mutate_provider_payload():
    payload = crux_url_payload()
    original = deepcopy(payload)
    normalize_crux_query_record_evidence_bound(
        payload,
        scope="url",
        source_url="https://example.com/page",
    )
    assert payload == original
