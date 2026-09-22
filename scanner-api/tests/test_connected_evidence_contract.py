from copy import deepcopy

import pytest

from app.connected_evidence_contract import validate_connected_evidence


def _evidence(*, state="verified", records=None, observed_at="2026-09-20T00:00:00Z"):
    unavailable = state in {"not_connected", "not_supported", "not_verified", "provider_error"}
    value = {
        "schema_version": "connected_evidence_v1",
        "provider": "example_provider",
        "surface": "example.surface",
        "method": "provided_payload_normalization",
        "source_kind": "example_rows",
        "state": state,
        "retrieved_at": "2026-09-21T20:30:00Z",
        "observed_at": None if unavailable else observed_at,
        "sample": (
            {"coverage_complete_claim": False}
            if unavailable
            else {"kind": "provider_rows", "coverage_complete_claim": False, "row_count": 1}
        ),
        "confidence": {
            "kind": "evidence_quality_not_statistical_probability",
            "level": "none" if unavailable else "first_party_provider_observed",
        },
        "provenance": {"transport": "provided_payload"},
        "coverage": {} if unavailable else {"row_count": 1},
        "records": [] if unavailable else (records if records is not None else [{"metric": 1}]),
    }
    if unavailable:
        value["reason"] = "provider evidence was unavailable"
    return value


def test_verified_contract_accepts_provenance_bearing_observations():
    evidence = _evidence()
    evidence["confidence"]["limitations"] = ["observational evidence only"]
    assert validate_connected_evidence(evidence) is evidence


@pytest.mark.parametrize("state", ["not_connected", "not_supported", "not_verified", "provider_error"])
def test_unavailable_states_are_explicit_and_record_free(state):
    evidence = _evidence(state=state)
    assert validate_connected_evidence(evidence)["state"] == state


def test_stale_state_retains_observations_with_source_timestamp():
    evidence = _evidence(state="stale", observed_at="2026-08-01T00:00:00Z")
    assert validate_connected_evidence(evidence)["records"] == [{"metric": 1}]


def test_missing_retrieval_timestamp_fails_closed():
    evidence = _evidence()
    evidence["retrieved_at"] = None
    with pytest.raises(ValueError, match="retrieved_at is required"):
        validate_connected_evidence(evidence)


def test_naive_timestamp_fails_closed():
    evidence = _evidence()
    evidence["retrieved_at"] = "2026-09-21T20:30:00"
    with pytest.raises(ValueError, match="timezone"):
        validate_connected_evidence(evidence)


def test_future_observation_relative_to_retrieval_fails_closed():
    evidence = _evidence(observed_at="2026-09-22T00:00:00Z")
    with pytest.raises(ValueError, match="later than retrieved_at"):
        validate_connected_evidence(evidence)


def test_verified_state_requires_observed_at():
    evidence = _evidence()
    evidence["observed_at"] = None
    with pytest.raises(ValueError, match="observed connected evidence requires observed_at"):
        validate_connected_evidence(evidence)


def test_unavailable_state_cannot_smuggle_records():
    evidence = _evidence(state="not_verified")
    evidence["records"] = [{"claimed_visibility": 1}]
    with pytest.raises(ValueError, match="cannot carry records"):
        validate_connected_evidence(evidence)


def test_unavailable_state_requires_reason():
    evidence = _evidence(state="not_connected")
    del evidence["reason"]
    with pytest.raises(ValueError, match="requires a reason"):
        validate_connected_evidence(evidence)


def test_unavailable_state_cannot_claim_sample_row_count():
    evidence = _evidence(state="not_verified")
    evidence["sample"]["row_count"] = 17
    with pytest.raises(ValueError, match="cannot claim sample observations"):
        validate_connected_evidence(evidence)


def test_unavailable_state_cannot_claim_complete_sample_coverage():
    evidence = _evidence(state="not_connected")
    evidence["sample"]["coverage_complete_claim"] = True
    with pytest.raises(ValueError, match="cannot claim sample observations"):
        validate_connected_evidence(evidence)


def test_unavailable_state_cannot_claim_coverage_window():
    evidence = _evidence(state="provider_error")
    evidence["coverage"] = {
        "period_start": "2026-09-01",
        "period_end": "2026-09-20",
        "row_count": 0,
    }
    with pytest.raises(ValueError, match="cannot claim coverage observations"):
        validate_connected_evidence(evidence)


def test_stale_state_requires_observed_at():
    evidence = _evidence(state="stale")
    evidence["observed_at"] = None
    with pytest.raises(ValueError, match="requires observed_at"):
        validate_connected_evidence(evidence)


def test_confidence_must_not_masquerade_as_statistical_probability():
    evidence = _evidence()
    evidence["confidence"]["kind"] = "probability"
    with pytest.raises(ValueError, match="evidence quality"):
        validate_connected_evidence(evidence)

    evidence = _evidence()
    evidence["confidence"]["probability"] = 0.99
    with pytest.raises(ValueError, match="confidence has unknown fields"):
        validate_connected_evidence(evidence)

    evidence = _evidence()
    evidence["confidence"]["level"] = "0.99"
    with pytest.raises(ValueError, match="registered evidence-quality level"):
        validate_connected_evidence(evidence)

    evidence = _evidence()
    evidence["confidence"]["limitations"] = "observational only"
    with pytest.raises(ValueError, match="confidence.limitations must be a bounded list"):
        validate_connected_evidence(evidence)


def test_explicit_sample_coverage_claim_is_required():
    evidence = _evidence()
    del evidence["sample"]["coverage_complete_claim"]
    with pytest.raises(ValueError, match="coverage_complete_claim"):
        validate_connected_evidence(evidence)


def test_unknown_top_level_field_requires_schema_revision():
    evidence = _evidence()
    evidence["ranking_score"] = 0.99
    with pytest.raises(ValueError, match="unknown fields"):
        validate_connected_evidence(evidence)


def test_validation_does_not_mutate_evidence():
    evidence = _evidence(records=[{"query": "technical seo", "clicks": 3}])
    before = deepcopy(evidence)
    validate_connected_evidence(evidence)
    assert evidence == before


def test_record_must_be_json_serializable():
    evidence = _evidence(records=[{"bad": object()}])
    with pytest.raises(ValueError, match="strict JSON-serializable"):
        validate_connected_evidence(evidence)


def test_record_rejects_non_finite_json_number():
    evidence = _evidence(records=[{"metric": float("nan")}])
    with pytest.raises(ValueError, match="strict JSON-serializable"):
        validate_connected_evidence(evidence)


def test_metadata_mappings_must_be_strict_json_serializable():
    evidence = _evidence()
    evidence["coverage"]["bad"] = float("inf")
    with pytest.raises(ValueError, match="coverage must be strict JSON-serializable"):
        validate_connected_evidence(evidence)


def test_provenance_requires_explicit_transport():
    evidence = _evidence()
    del evidence["provenance"]["transport"]
    with pytest.raises(ValueError, match="provenance.transport"):
        validate_connected_evidence(evidence)


def test_unavailable_state_may_omit_transport_when_nothing_was_observed():
    evidence = _evidence(state="not_connected")
    evidence["provenance"] = {}
    assert validate_connected_evidence(evidence)["state"] == "not_connected"


def test_unavailable_state_cannot_claim_observation_timestamp():
    evidence = _evidence(state="not_verified")
    evidence["observed_at"] = "2026-09-20T00:00:00Z"
    with pytest.raises(ValueError, match="cannot claim observed_at"):
        validate_connected_evidence(evidence)


def test_stale_observation_must_predate_retrieval():
    evidence = _evidence(state="stale", observed_at="2026-09-21T20:30:00Z")
    with pytest.raises(ValueError, match="must predate retrieved_at"):
        validate_connected_evidence(evidence)


def test_metadata_mapping_size_is_bounded():
    evidence = _evidence()
    evidence["provenance"]["blob"] = "x" * 140_000
    with pytest.raises(ValueError, match="provenance exceeds its size bound"):
        validate_connected_evidence(evidence)
