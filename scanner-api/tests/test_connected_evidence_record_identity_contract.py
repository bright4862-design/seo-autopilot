from copy import deepcopy

import pytest

from app.connected_evidence_record_identity_contract import (
    RECORD_IDENTITY_VERSION,
    connected_evidence_record_identity,
    validate_connected_evidence_record_identity_semantics,
)


def _base(*, provider, source_kind, coverage, records, state="verified"):
    return {
        "schema_version": "connected_evidence_v1",
        "provider": provider,
        "surface": "unused-by-stub",
        "method": "unused-by-stub",
        "source_kind": source_kind,
        "state": state,
        "retrieved_at": "2026-09-21T20:30:00Z",
        "observed_at": None if state == "not_verified" else "2026-09-20T00:00:00Z",
        "sample": {"coverage_complete_claim": False},
        "confidence": {"kind": "evidence_quality_not_statistical_probability", "level": "x"},
        "provenance": {},
        "coverage": coverage,
        "records": records,
    }


def _gsc(records, state="verified"):
    return _base(
        provider="google_search_console",
        source_kind="search_analytics",
        coverage={"dimensions": ["date", "query"], "period_start": "2026-09-20", "period_end": "2026-09-20"},
        records=records,
        state=state,
    )


def _bing(records):
    return _base(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        coverage={"period_end": "2026-09-20"},
        records=records,
    )


def _ga4(records):
    return _base(
        provider="google_analytics_4",
        source_kind="ai_assistant_referrals",
        coverage={"period_end": "2026-09-20"},
        records=records,
    )


def _inspection(records):
    return _base(
        provider="google_search_console",
        source_kind="url_inspection",
        coverage={"url_count": 1},
        records=records,
    )


@pytest.fixture
def bypass_upstream(monkeypatch):
    import app.connected_evidence_record_identity_contract as contract

    seen = []

    def _accept(evidence):
        seen.append(evidence)
        return evidence

    monkeypatch.setattr(contract, "validate_connected_evidence_scope_semantics", _accept)
    return seen


def test_record_identity_contract_is_versioned_non_mutating_and_deterministic(bypass_upstream):
    evidence = _gsc([
        {"dimensions": {"date": "2026-09-20", "query": "technical seo"}, "row_number": 1},
    ])
    before = deepcopy(evidence)
    assert RECORD_IDENTITY_VERSION == "connected_evidence_record_identity_v1"
    first = connected_evidence_record_identity(evidence, evidence["records"][0], index=0)
    second = connected_evidence_record_identity(evidence, evidence["records"][0], index=0)
    assert first == second
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence
    assert evidence == before


def test_gsc_duplicate_dimension_population_fails_closed(bypass_upstream):
    evidence = _gsc([
        {"dimensions": {"date": "2026-09-20", "query": "technical seo"}, "row_number": 1},
        {"dimensions": {"query": "technical seo", "date": "2026-09-20"}, "row_number": 9},
    ])
    with pytest.raises(ValueError, match="duplicate connected-evidence logical record"):
        validate_connected_evidence_record_identity_semantics(evidence)


def test_gsc_distinct_query_identity_is_allowed(bypass_upstream):
    evidence = _gsc([
        {"dimensions": {"date": "2026-09-20", "query": "technical seo"}, "row_number": 1},
        {"dimensions": {"date": "2026-09-20", "query": "seo audit"}, "row_number": 2},
    ])
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence


def test_bing_duplicate_provider_dimensions_fail_even_when_metrics_or_row_number_differ(bypass_upstream):
    common = {
        "kind": "grounding_query_page",
        "date": "2026-09-20",
        "url": "https://example.test/a",
        "grounding_query": "best seo audit",
        "topic": "seo",
        "intent": "commercial",
        "geography": None,
        "country": "US",
        "region": None,
        "market": "en-US",
        "surface": "copilot",
    }
    first = {**common, "citations": 1, "row_number": 1}
    second = {**common, "citations": 7, "row_number": 44}
    with pytest.raises(ValueError, match="duplicate connected-evidence logical record"):
        validate_connected_evidence_record_identity_semantics(_bing([first, second]))


def test_bing_distinct_geography_is_not_collapsed(bypass_upstream):
    first = {
        "kind": "grounding_query",
        "date": "2026-09-20",
        "url": None,
        "grounding_query": "best seo audit",
        "topic": None,
        "intent": None,
        "geography": None,
        "country": "US",
        "region": None,
        "market": "en-US",
        "surface": "copilot",
        "row_number": 1,
    }
    second = {**first, "country": "FR", "market": "fr-FR", "row_number": 2}
    evidence = _bing([first, second])
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence


def test_ga4_duplicate_dimension_population_fails_closed(bypass_upstream):
    common = {
        "assistant": "chatgpt",
        "date": "2026-09-20",
        "source": "chatgpt.com / referral",
        "medium": "referral",
        "landing_page": "/pricing",
        "geography": None,
        "country": "US",
        "region": None,
        "device_category": "desktop",
    }
    first = {**common, "sessions": 2, "row_number": 1}
    second = {**common, "sessions": 8, "row_number": 2}
    with pytest.raises(ValueError, match="duplicate connected-evidence logical record"):
        validate_connected_evidence_record_identity_semantics(_ga4([first, second]))


def test_ga4_registered_assistant_aliases_cannot_evade_duplicate_identity(bypass_upstream):
    common = {
        "date": "2026-09-20",
        "source": "copilot.microsoft.com / referral",
        "medium": "referral",
        "landing_page": "/pricing",
        "geography": None,
        "country": "US",
        "region": None,
        "device_category": "desktop",
    }
    first = {**common, "assistant": "copilot", "sessions": 2, "row_number": 1}
    second = {**common, "assistant": "Microsoft Copilot", "sessions": 8, "row_number": 2}
    with pytest.raises(ValueError, match="duplicate connected-evidence logical record"):
        validate_connected_evidence_record_identity_semantics(_ga4([first, second]))


def test_ga4_unregistered_assistant_fails_closed_at_identity_boundary(bypass_upstream):
    evidence = _ga4([
        {
            "assistant": "random bot",
            "date": "2026-09-20",
            "source": None,
            "medium": "referral",
            "landing_page": "/pricing",
            "geography": None,
            "country": "US",
            "region": None,
            "device_category": "desktop",
            "sessions": 1,
            "row_number": 1,
        }
    ])
    with pytest.raises(ValueError, match="registered AI assistant"):
        validate_connected_evidence_record_identity_semantics(evidence)


def test_ga4_distinct_landing_page_is_allowed(bypass_upstream):
    first = {
        "assistant": "chatgpt",
        "date": "2026-09-20",
        "source": "chatgpt.com",
        "medium": "referral",
        "landing_page": "/pricing",
        "geography": None,
        "country": None,
        "region": None,
        "device_category": None,
        "row_number": 1,
    }
    second = {**first, "landing_page": "/features", "row_number": 2}
    evidence = _ga4([first, second])
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence


def test_url_inspection_identity_is_stable(bypass_upstream):
    evidence = _inspection([{"inspection_url": "https://example.test/a"}])
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence


def test_unavailable_evidence_skips_record_identity_population(bypass_upstream):
    evidence = _gsc([], state="not_verified")
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence


def test_unknown_profile_fails_closed(bypass_upstream):
    evidence = _base(
        provider="unknown",
        source_kind="unknown",
        coverage={},
        records=[{"row_number": 1}],
    )
    with pytest.raises(ValueError, match="unsupported connected-evidence"):
        validate_connected_evidence_record_identity_semantics(evidence)
