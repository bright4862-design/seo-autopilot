from copy import deepcopy

from app.nextgen_browser_performance_source_binding import (
    SOURCE_BINDING_VERSION,
    validate_performance_observation_source_binding,
)


def _sample(*urls):
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


def _field(source_url="https://e.test/a", *, scope="url", state="connected"):
    return {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "CrUX",
        "state": state,
        "reason": None,
        "scope": scope,
        "observed_at": "2026-09-22T05:00:00Z",
        "source_url": source_url,
        "metrics": (
            {"lcp": {"value": 2400.0, "unit": "ms", "rating": "good"}}
            if state == "connected"
            else None
        ),
    }


def _lab(source_url="https://e.test/a", *, state="connected"):
    return {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "Lighthouse",
        "state": state,
        "reason": None,
        "observed_at": "2026-09-22T05:00:00Z",
        "source_url": source_url,
        "performance_score": 91.0 if state == "connected" else None,
        "metrics": None,
        "opportunities": [],
    }


def _provenance(**overrides):
    value = {
        "version": "nextgen_pagespeed_provenance_v1",
        "requested_url": "https://e.test/a",
        "response_final_url": "https://e.test/final",
        "field_source_url": "https://e.test/final",
        "field_initial_url": "https://e.test/a",
        "field_origin_fallback": False,
        "lighthouse_requested_url": "https://e.test/a",
        "lighthouse_final_url": "https://e.test/final",
        "analysis_timestamp": "2026-09-22T05:00:00Z",
        "lighthouse_fetch_time": "2026-09-22T04:59:59Z",
        "lighthouse_version": "13.0.0",
        "strategy": "mobile",
    }
    value.update(overrides)
    return value


def test_same_source_field_and_lab_bind_to_sampled_request():
    result = validate_performance_observation_source_binding(
        _sample("https://E.TEST/a#fragment"),
        [{"requested_url": "https://e.test/a", "field": _field(), "lab": _lab()}],
    )
    assert result["version"] == SOURCE_BINDING_VERSION
    assert result["valid"] is True
    assert result["bound_observations"] == 1
    assert result["observation_errors"] == []


def test_url_scoped_field_from_foreign_page_fails_without_redirect_provenance():
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"),
        [{
            "requested_url": "https://e.test/a",
            "field": _field("https://foreign.test/a"),
        }],
    )
    assert result["valid"] is False
    assert result["observation_errors"][0]["reasons"] == ["field_source_identity_mismatch"]


def test_origin_scoped_field_for_requested_origin_is_valid():
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"),
        [{
            "requested_url": "https://e.test/a",
            "field": _field("https://e.test/", scope="origin"),
        }],
    )
    assert result["valid"] is True


def test_origin_scope_requires_an_origin_identity_not_a_page_path():
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"),
        [{
            "requested_url": "https://e.test/a",
            "field": _field("https://e.test/path", scope="origin"),
        }],
    )
    assert result["valid"] is False
    assert "field_origin_scope_source_not_origin" in result["observation_errors"][0]["reasons"]


def test_cross_origin_field_redirect_requires_matching_explicit_provenance():
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"),
        [{
            "requested_url": "https://e.test/a",
            "field": _field("https://other.test/", scope="origin"),
            "provenance": _provenance(
                response_final_url="https://other.test/final",
                field_source_url="https://other.test/",
                lighthouse_final_url="https://other.test/final",
            ),
        }],
    )
    assert result["valid"] is True


def test_lighthouse_redirected_final_identity_requires_matching_provenance():
    valid = {
        "requested_url": "https://e.test/a",
        "lab": _lab("https://e.test/final"),
        "provenance": _provenance(),
    }
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"), [valid]
    )
    assert result["valid"] is True

    missing = deepcopy(valid)
    del missing["provenance"]
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"), [missing]
    )
    assert result["valid"] is False
    assert result["observation_errors"][0]["reasons"] == ["lab_source_identity_mismatch"]


def test_tampered_provenance_requested_identity_fails_closed():
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"),
        [{
            "requested_url": "https://e.test/a",
            "lab": _lab(),
            "provenance": _provenance(requested_url="https://foreign.test/a"),
        }],
    )
    assert result["valid"] is False
    assert "provenance_requested_identity_mismatch" in result["observation_errors"][0]["reasons"]


def test_non_connected_component_does_not_claim_measurement_source_binding():
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"),
        [{
            "requested_url": "https://e.test/a",
            "field": _field("https://foreign.test/x", state="unavailable"),
        }],
    )
    assert result["valid"] is True
    assert result["bound_observations"] == 1


def test_duplicate_requested_identity_fails_closed():
    row = {"requested_url": "https://e.test/a", "field": _field()}
    result = validate_performance_observation_source_binding(
        _sample("https://e.test/a"),
        [row, deepcopy(row)],
    )
    assert result["valid"] is False
    assert result["observation_errors"] == [{
        "index": 1,
        "requested_url": "https://e.test/a",
        "reasons": ["requested_identity_duplicate"],
    }]


def test_inputs_are_not_mutated():
    sample = _sample("https://e.test/a")
    observations = [{"requested_url": "https://e.test/a", "field": _field()}]
    before_sample = deepcopy(sample)
    before_observations = deepcopy(observations)
    validate_performance_observation_source_binding(sample, observations)
    assert sample == before_sample
    assert observations == before_observations
