from copy import deepcopy

from app.nextgen_browser_performance_evidence_coverage import (
    summarize_performance_evidence_coverage,
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


def _field(state="connected"):
    return {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "CrUX",
        "state": state,
        "reason": None,
        "scope": "url",
        "observed_at": "2026-09-22T05:00:00Z",
        "source_url": "https://e.test/a",
        "metrics": (
            {"lcp": {"value": 2400.0, "unit": "ms", "rating": "good"}}
            if state == "connected"
            else None
        ),
    }


def _lab(state="connected"):
    return {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "Lighthouse",
        "state": state,
        "reason": None,
        "observed_at": "2026-09-22T05:00:00Z",
        "source_url": "https://e.test/a",
        "performance_score": 91.0 if state == "connected" else None,
        "metrics": None,
        "opportunities": [],
    }


def test_coverage_keeps_field_and_lab_assessment_separate():
    coverage = summarize_performance_evidence_coverage(
        _sample("https://E.TEST/a#x", "https://e.test/b"),
        [
            {"requested_url": "https://e.test/a", "field": _field(), "lab": _lab()},
            {"requested_url": "https://e.test/b", "field": _field("unavailable")},
        ],
    )
    assert coverage["state"] == "available"
    assert coverage["selected_urls"] == ["https://e.test/a", "https://e.test/b"]
    assert coverage["field"]["coverage_state"] == "complete"
    assert coverage["field"]["attempted_pages"] == 2
    assert coverage["field"]["connected_pages"] == 1
    assert coverage["field"]["state_counts"]["unavailable"] == 1
    assert coverage["lab"]["coverage_state"] == "partial"
    assert coverage["lab"]["attempted_pages"] == 1
    assert coverage["lab"]["unassessed_urls"] == ["https://e.test/b"]


def test_non_connected_provider_states_are_attempted_but_not_measured():
    coverage = summarize_performance_evidence_coverage(
        _sample("https://e.test/a", "https://e.test/b"),
        [
            {"requested_url": "https://e.test/a", "field": _field("rate_limited")},
            {"requested_url": "https://e.test/b", "field": _field("provider_error")},
        ],
    )
    assert coverage["field"]["coverage_state"] == "complete"
    assert coverage["field"]["attempted_ratio"] == 1.0
    assert coverage["field"]["connected_pages"] == 0
    assert coverage["field"]["connected_ratio"] == 0.0
    assert coverage["field"]["state_counts"]["rate_limited"] == 1
    assert coverage["field"]["state_counts"]["provider_error"] == 1


def test_selected_pages_without_observations_remain_unassessed():
    coverage = summarize_performance_evidence_coverage(_sample("https://e.test/a"), [])
    assert coverage["field"]["coverage_state"] == "unassessed"
    assert coverage["field"]["unassessed_urls"] == ["https://e.test/a"]
    assert coverage["lab"]["coverage_state"] == "unassessed"
    assert coverage["lab"]["connected_ratio"] == 0.0


def test_empty_selected_population_is_not_applicable():
    coverage = summarize_performance_evidence_coverage(_sample(), [])
    assert coverage["state"] == "not_applicable"
    assert coverage["reason"] == "no_selected_pages"
    assert coverage["field"]["coverage_state"] == "not_applicable"
    assert coverage["field"]["attempted_ratio"] is None
    assert coverage["lab"]["connected_ratio"] is None


def test_foreign_requested_identity_fails_aggregate_closed():
    coverage = summarize_performance_evidence_coverage(
        _sample("https://e.test/a"),
        [{"requested_url": "https://foreign.test/a", "field": _field()}],
    )
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "performance_observation_binding_invalid"
    assert coverage["field"]["attempted_pages"] is None
    assert coverage["details"]["foreign_requested_urls"] == ["https://foreign.test/a"]


def test_duplicate_observation_for_one_selected_page_fails_closed():
    row = {"requested_url": "https://e.test/a", "field": _field()}
    coverage = summarize_performance_evidence_coverage(
        _sample("https://e.test/a"), [row, deepcopy(row)]
    )
    assert coverage["state"] == "not_verified"
    assert coverage["details"]["duplicate_requested_urls"] == ["https://e.test/a"]


def test_invalid_component_contract_fails_aggregate_closed():
    invalid = _field()
    invalid["metrics"] = None
    coverage = summarize_performance_evidence_coverage(
        _sample("https://e.test/a"),
        [{"requested_url": "https://e.test/a", "field": invalid}],
    )
    assert coverage["state"] == "not_verified"
    assert coverage["details"]["malformed_observations"] == [
        {"index": 0, "reasons": ["field:connected_metrics_missing"]}
    ]


def test_observation_without_field_or_lab_component_fails_closed():
    coverage = summarize_performance_evidence_coverage(
        _sample("https://e.test/a"), [{"requested_url": "https://e.test/a"}]
    )
    assert coverage["state"] == "not_verified"
    assert coverage["details"]["malformed_observations"] == [
        {"index": 0, "reasons": ["observation_without_components"]}
    ]


def test_inputs_are_not_mutated():
    sample = _sample("https://e.test/a")
    observations = [{"requested_url": "https://e.test/a", "field": _field()}]
    before_sample = deepcopy(sample)
    before_observations = deepcopy(observations)
    summarize_performance_evidence_coverage(sample, observations)
    assert sample == before_sample
    assert observations == before_observations
