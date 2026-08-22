"""Patch C part 2 - a limited scan reaches the limited path, not the failure path.

Part 1 makes a thin crawl provisional. persistDurableScanAuthority refuses
anything that is not release-eligible, so without this routing Tanners and
Decathlon would stop being wrongly authoritative and start being outright
failures -- losing evidence that was real. That is a worse answer than the
overclaim it replaced, which is exactly what the blueprint warns about.
"""
from app.scan_job import (
    LIMITED_COMPLETION_VERSION,
    LIMITED_COVERAGE_STATES,
    build_limited_envelope,
    coverage_state_of,
    limited_result_payload,
)


def review(state="limited_coverage", *, reasons=None, fixes=1, eligible=False):
    return {
        "scan_status": "inconclusive_insufficient_evidence",
        "health_score": 48,
        "health_grade": "Insufficient evidence",
        "limitation": "FixList reviewed 38 of 3,689 discovered pages.",
        "release_gate_eligible": eligible,
        "score_is_provisional": not eligible,
        "recommendations": [{"fix_id": f"fix_{i}", "issue_title": f"F{i}"} for i in range(fixes)],
        "site_fingerprint": {
            "coverage_assessment": {
                "state": state,
                "reasons": reasons or ["retained_pages_below_minimum"],
                "coverage_authority_version": "coverage_authority_v1_shared_decision",
            },
        },
    }


def test_the_limited_states_are_the_non_sufficient_ones():
    assert LIMITED_COVERAGE_STATES == {"limited_coverage", "inventory_unproven", "access_limited"}


def test_the_coverage_state_is_read_from_the_shared_assessment():
    assert coverage_state_of(review("inventory_unproven")) == "inventory_unproven"
    assert coverage_state_of({}) == ""


def test_the_limited_payload_binds_the_limitation_and_its_reasons():
    """The limitation is the point of the record, so the proof must cover it."""
    payload = limited_result_payload(review(reasons=["retained_pages_below_minimum", "coverage_ratio_below_minimum"]))

    assert payload["coverage_state"] == "limited_coverage"
    assert payload["coverage_reasons"] == ["retained_pages_below_minimum", "coverage_ratio_below_minimum"]
    assert payload["coverage_authority_version"] == "coverage_authority_v1_shared_decision"
    assert payload["release_gate_eligible"] is False
    assert payload["score_is_provisional"] is True
    assert payload["limitation"]


def test_the_limited_envelope_is_its_own_version_not_the_authority_one():
    envelope = build_limited_envelope(
        {"id": "scan_1", "project_id": "p", "owner_user_id": "o", "attempt_count": 1},
        {"normalized_domain": "www.example.com"},
        review(),
        "signing-key-never-deployed",
    )

    assert envelope["version"] == LIMITED_COMPLETION_VERSION
    assert envelope["version"] != "durable_standard150_completion_v1"
    assert envelope["proof"]
    assert envelope["identity"]["scan_id"] == "scan_1"
    assert envelope["identity"]["normalized_domain"] == "example.com"


def test_the_envelope_never_carries_an_authoritative_review():
    envelope = build_limited_envelope(
        {"id": "scan_1", "project_id": "p", "owner_user_id": "o", "attempt_count": 1},
        {},
        review(),
        "signing-key-never-deployed",
    )
    assert envelope["review"]["release_gate_eligible"] is False


def test_the_worker_routes_limited_coverage_to_the_limited_function():
    """Read from the source: the call must exist and target the right package."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "scan_job.py").read_text(encoding="utf-8")
    assert 'invoke_function(client, "persistLimitedScanResult"' in source
    assert "LIMITED_COVERAGE_STATES" in source


def test_a_sufficient_scan_never_takes_the_limited_path():
    assert coverage_state_of(review("sufficient", eligible=True)) not in LIMITED_COVERAGE_STATES
