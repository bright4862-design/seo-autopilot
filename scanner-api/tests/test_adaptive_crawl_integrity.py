from copy import deepcopy

from app.adaptive_crawl import build_tranche_yield_telemetry, continuation_decision
from app.adaptive_crawl_integrity import (
    ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
    validate_tranche_telemetry,
    verified_continuation_decision,
)


def _snapshot(assessed_count, *, route_count=1, template_count=1, graph_count=1, finding_count=1):
    return {
        "assessed_count": assessed_count,
        "route_signatures": {f"r{i}" for i in range(route_count)},
        "template_keys": {f"t{i}" for i in range(template_count)},
        "graph_edges": {f"e{i}" for i in range(graph_count)},
        "finding_fingerprints": {f"f{i}" for i in range(finding_count)},
        "high_impact_finding_fingerprints": {f"h{i}" for i in range(finding_count)},
        "high_value_families_assessed": {"product_page"},
    }


def _observed_telemetry():
    return build_tranche_yield_telemetry(
        _snapshot(150),
        _snapshot(500, route_count=50, template_count=10, graph_count=100, finding_count=20),
        discovered_urls=1800,
    )


def test_valid_builder_telemetry_passes_integrity_and_preserves_continuation_policy():
    telemetry = _observed_telemetry()
    integrity = validate_tranche_telemetry(telemetry)
    expected = continuation_decision(telemetry)
    actual = verified_continuation_decision(telemetry)

    assert integrity == {
        "version": ADAPTIVE_TELEMETRY_INTEGRITY_VERSION,
        "valid": True,
        "reason": "telemetry_integrity_verified",
    }
    assert {key: value for key, value in actual.items() if key != "integrity_version"} == expected
    assert actual["integrity_version"] == ADAPTIVE_TELEMETRY_INTEGRITY_VERSION


def test_forged_high_novelty_rate_cannot_authorize_expansion():
    telemetry = _observed_telemetry()
    telemetry["new_route_signatures_per_100"] = 999.0

    decision = verified_continuation_decision(telemetry)

    assert decision["decision"] == "insufficient_evidence"
    assert decision["next_target"] is None
    assert decision["reason"] == "telemetry_integrity_failed:rate_mismatch:new_route_signatures_per_100"


def test_non_finite_rate_fails_closed():
    telemetry = _observed_telemetry()
    telemetry["new_graph_edges_per_100"] = float("nan")

    integrity = validate_tranche_telemetry(telemetry)

    assert integrity["valid"] is False
    assert integrity["reason"] == "invalid_rate:new_graph_edges_per_100"


def test_string_or_boolean_counts_do_not_cross_integrity_boundary():
    for bad_value in ("500", True):
        telemetry = _observed_telemetry()
        telemetry["assessed_count"] = bad_value
        integrity = validate_tranche_telemetry(telemetry)
        assert integrity["valid"] is False
        assert integrity["reason"] == "invalid_count_type"


def test_pages_added_must_equal_assessed_delta():
    telemetry = _observed_telemetry()
    telemetry["pages_added"] += 1

    integrity = validate_tranche_telemetry(telemetry)

    assert integrity["valid"] is False
    assert integrity["reason"] == "pages_added_mismatch"


def test_observed_state_cannot_hide_a_missing_delta():
    telemetry = _observed_telemetry()
    telemetry["new_template_keys"] = None
    telemetry["new_template_keys_per_100"] = None

    integrity = validate_tranche_telemetry(telemetry)

    assert integrity["valid"] is False
    assert integrity["reason"] == "observed_missing_delta:new_template_keys"


def test_rate_cannot_exist_without_corresponding_delta():
    telemetry = build_tranche_yield_telemetry(
        {"assessed_count": 150, "route_signatures": {"r0"}},
        {"assessed_count": 500, "route_signatures": {"r0", "r1"}},
        discovered_urls=1800,
    )
    telemetry["new_template_keys_per_100"] = 1.0

    integrity = validate_tranche_telemetry(telemetry)

    assert integrity["valid"] is False
    assert integrity["reason"] == "rate_without_delta:new_template_keys_per_100"


def test_honest_incomplete_evidence_remains_valid_but_cannot_expand():
    telemetry = build_tranche_yield_telemetry(
        {"assessed_count": 150, "route_signatures": {"r0"}},
        {"assessed_count": 500, "route_signatures": {"r0", "r1"}},
        discovered_urls=1800,
    )

    integrity = validate_tranche_telemetry(telemetry)
    decision = verified_continuation_decision(telemetry)

    assert integrity["valid"] is True
    assert decision["decision"] == "insufficient_evidence"
    assert decision["reason"] == "marginal_yield_signals_incomplete"
    assert decision["site_fully_understood"] is False


def test_regressed_keys_cannot_be_hidden_by_forging_monotonic_flag():
    telemetry = _observed_telemetry()
    telemetry["regressed_signal_keys"] = ("template_keys",)
    telemetry["evidence_monotonic"] = True

    integrity = validate_tranche_telemetry(telemetry)

    assert integrity["valid"] is False
    assert integrity["reason"] == "regressed_signal_keys_present"


def test_integrity_check_does_not_mutate_telemetry():
    telemetry = _observed_telemetry()
    original = deepcopy(telemetry)

    validate_tranche_telemetry(telemetry)

    assert telemetry == original
