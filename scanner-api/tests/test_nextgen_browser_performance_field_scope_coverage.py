from copy import deepcopy

import pytest

import app.nextgen_browser_performance_field_scope_coverage as scope_module
from app.nextgen_browser_performance_field_scope_coverage import (
    FIELD_SCOPE_COVERAGE_INTEGRITY_VERSION,
    FIELD_SCOPE_COVERAGE_VERSION,
    summarize_field_scope_coverage,
    validate_field_scope_coverage_contract,
)


def sample(*urls):
    pages = [
        {
            "url": url,
            "template_family": f"family_{index}",
            "high_value_weight": 1.0,
            "selection_reason": "template_representative",
        }
        for index, url in enumerate(urls)
    ]
    count = len(pages)
    return {
        "version": "nextgen_performance_sample_v1",
        "requested_max_pages": count,
        "max_pages": count,
        "hard_cap": 12,
        "eligible_page_observations": count,
        "duplicate_page_observations_dropped": 0,
        "eligible_pages": count,
        "template_families": count,
        "selected_pages": count,
        "template_coverage_complete": True,
        "omitted_template_families": [],
        "pages": pages,
    }


def field(scope="url", source="https://example.com/a", state="connected"):
    return {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "CrUX",
        "state": state,
        "reason": None if state == "connected" else state,
        "scope": scope,
        "observed_at": "2026-09-23T00:00:00Z",
        "source_url": source,
        "metrics": {
            "lcp": {"value": 2400.0, "unit": "ms", "rating": "good"}
        } if state == "connected" else None,
    }


def observation(url, *, field_evidence=None, lab=None):
    row = {"requested_url": url}
    if field_evidence is not None:
        row["field"] = field_evidence
    if lab is not None:
        row["lab"] = lab
    return row


@pytest.fixture(autouse=True)
def provider_binding_is_already_valid(monkeypatch):
    monkeypatch.setattr(
        scope_module,
        "validate_performance_observation_provider_binding",
        lambda sample, observations: {
            "valid": True,
            "reasons": [],
            "observation_errors": [],
        },
    )


def test_exact_url_scope_is_page_level_coverage():
    s = sample("https://example.com/a")
    result = summarize_field_scope_coverage(
        s, [observation("https://example.com/a", field_evidence=field())]
    )
    assert result["version"] == FIELD_SCOPE_COVERAGE_VERSION
    assert result["field"]["page_level_connected_pages"] == 1
    assert result["field"]["page_level_connected_ratio"] == 1.0
    assert result["field"]["origin_scoped_selected_pages"] == 0


def test_origin_scope_never_inflates_page_level_coverage_and_dedupes_origin():
    s = sample("https://example.com/a", "https://example.com/b")
    origin_field = field("origin", "https://example.com/")
    result = summarize_field_scope_coverage(s, [
        observation("https://example.com/a", field_evidence=deepcopy(origin_field)),
        observation("https://example.com/b", field_evidence=deepcopy(origin_field)),
    ])
    assert result["field"]["connected_observations"] == 2
    assert result["field"]["origin_scoped_selected_pages"] == 2
    assert result["field"]["unique_origin_sources"] == 1
    assert result["field"]["page_level_connected_pages"] == 0
    assert result["field"]["page_level_connected_ratio"] == 0.0
    assert result["field"]["origin_groups"] == [{
        "origin": "https://example.com/",
        "requested_urls": ["https://example.com/a", "https://example.com/b"],
    }]


def test_redirected_url_scope_is_context_but_not_exact_page_coverage():
    s = sample("https://example.com/start")
    result = summarize_field_scope_coverage(s, [observation(
        "https://example.com/start",
        field_evidence=field("url", "https://example.com/final"),
    )])
    assert result["field"]["connected_observations"] == 1
    assert result["field"]["url_scoped_redirected_pages"] == 1
    assert result["field"]["page_level_connected_pages"] == 0
    assert result["field"]["redirected_url_scoped_requests"] == [{
        "requested_url": "https://example.com/start",
        "field_source_url": "https://example.com/final",
    }]


def test_non_connected_field_is_attempted_but_unmeasured():
    s = sample("https://example.com/a")
    result = summarize_field_scope_coverage(s, [observation(
        "https://example.com/a",
        field_evidence=field("url", "https://example.com/a", "rate_limited"),
    )])
    assert result["field"]["attempted_pages"] == 1
    assert result["field"]["connected_observations"] == 0
    assert result["field"]["non_connected_pages"] == 1
    assert result["field"]["state_counts"]["rate_limited"] == 1


def test_lab_only_observation_leaves_field_unassessed():
    s = sample("https://example.com/a")
    result = summarize_field_scope_coverage(s, [observation(
        "https://example.com/a", lab={"state": "connected"}
    )])
    assert result["field"]["attempted_pages"] == 0
    assert result["field"]["unassessed_pages"] == 1
    assert result["field"]["page_level_connected_pages"] == 0


def test_mixed_scope_ratios_keep_observation_and_page_coverage_distinct():
    s = sample(
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
        "https://example.com/d",
    )
    result = summarize_field_scope_coverage(s, [
        observation("https://example.com/a", field_evidence=field("url", "https://example.com/a")),
        observation("https://example.com/b", field_evidence=field("origin", "https://example.com/")),
        observation(
            "https://example.com/c",
            field_evidence=field("url", "https://example.com/c", "unavailable"),
        ),
    ])
    assert result["field"]["connected_observation_ratio"] == 0.5
    assert result["field"]["page_level_connected_ratio"] == 0.25
    assert result["field"]["unassessed_urls"] == ["https://example.com/d"]


def test_distinct_origin_sources_are_counted_once_each():
    s = sample("https://a.example/x", "https://b.example/y")
    result = summarize_field_scope_coverage(s, [
        observation("https://a.example/x", field_evidence=field("origin", "https://a.example/")),
        observation("https://b.example/y", field_evidence=field("origin", "https://b.example/")),
    ])
    assert result["field"]["unique_origin_sources"] == 2
    assert [row["origin"] for row in result["field"]["origin_groups"]] == [
        "https://a.example/",
        "https://b.example/",
    ]


def test_default_port_normalization_preserves_exact_page_identity():
    s = sample("https://example.com/a")
    result = summarize_field_scope_coverage(s, [observation(
        "https://example.com:443/a",
        field_evidence=field("url", "https://example.com:443/a"),
    )])
    assert result["field"]["page_level_connected_urls"] == ["https://example.com/a"]


def test_observation_order_does_not_change_scope_coverage():
    s = sample("https://example.com/a", "https://example.com/b")
    first = observation(
        "https://example.com/a", field_evidence=field("origin", "https://example.com/")
    )
    second = observation(
        "https://example.com/b", field_evidence=field("url", "https://example.com/b")
    )
    assert summarize_field_scope_coverage(s, [first, second]) == summarize_field_scope_coverage(
        s, [second, first]
    )


def test_empty_sample_is_not_applicable_without_claiming_coverage():
    result = summarize_field_scope_coverage(sample(), [])
    assert result["state"] == "not_applicable"
    assert result["field"]["page_level_connected_ratio"] is None
    assert result["field"]["connected_observation_ratio"] is None


def test_invalid_sample_fails_closed_before_scope_accounting():
    s = sample("https://example.com/a")
    s["selected_pages"] = 2
    result = summarize_field_scope_coverage(s, [])
    assert result["state"] == "not_verified"
    assert result["reason"] == "sample_contract_invalid"
    assert result["field"]["page_level_connected_pages"] is None


def test_invalid_provider_binding_fails_closed(monkeypatch):
    monkeypatch.setattr(
        scope_module,
        "validate_performance_observation_provider_binding",
        lambda sample, observations: {
            "valid": False,
            "reasons": ["performance_observation_provider_binding_invalid"],
            "observation_errors": [{"index": 0, "reasons": ["field_component_provider_mismatch"]}],
        },
    )
    s = sample("https://example.com/a")
    result = summarize_field_scope_coverage(
        s, [observation("https://example.com/a", field_evidence=field())]
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "performance_observation_provider_binding_invalid"
    assert result["field"]["page_level_connected_pages"] is None


def test_integrity_recomputes_and_rejects_page_coverage_tampering():
    s = sample("https://example.com/a")
    observations = [observation("https://example.com/a", field_evidence=field())]
    evidence = summarize_field_scope_coverage(s, observations)
    forged = deepcopy(evidence)
    forged["field"]["page_level_connected_ratio"] = 0.0
    result = validate_field_scope_coverage_contract(s, observations, forged)
    assert result == {
        "version": FIELD_SCOPE_COVERAGE_INTEGRITY_VERSION,
        "valid": False,
        "reasons": ["field_scope_coverage_mismatch"],
    }


def test_integrity_accepts_truthful_fail_closed_evidence(monkeypatch):
    monkeypatch.setattr(
        scope_module,
        "validate_performance_observation_provider_binding",
        lambda sample, observations: {
            "valid": False,
            "reasons": ["binding_invalid"],
            "observation_errors": [],
        },
    )
    s = sample("https://example.com/a")
    observations = [observation("https://example.com/a", field_evidence=field())]
    evidence = summarize_field_scope_coverage(s, observations)
    result = validate_field_scope_coverage_contract(s, observations, evidence)
    assert evidence["state"] == "not_verified"
    assert result["valid"] is True


def test_scope_accounting_and_integrity_do_not_mutate_inputs():
    s = sample("https://example.com/a", "https://example.com/b")
    observations = [
        observation("https://example.com/a", field_evidence=field("origin", "https://example.com/")),
        observation("https://example.com/b", field_evidence=field("url", "https://example.com/b")),
    ]
    before_sample = deepcopy(s)
    before_observations = deepcopy(observations)
    evidence = summarize_field_scope_coverage(s, observations)
    validate_field_scope_coverage_contract(s, observations, evidence)
    assert s == before_sample
    assert observations == before_observations
