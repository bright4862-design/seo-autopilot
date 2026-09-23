from copy import deepcopy

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_transport_candidate import build_geo_v8_transport_candidate
from app.geo_v8_transport_observation_binding import (
    VERSION,
    build_geo_v8_transport_observation_binding,
    serialize_geo_v8_transport_observation_binding,
    validate_geo_v8_transport_observation_binding,
    validate_geo_v8_transport_observation_binding_reload_identity,
)
from app.geo_v8_transport_sources import validate_geo_v8_transport_sources


PAGE_IDS = ("p_one", "p_two")


def observations(*, swap_search_policy=False, evidence_suffix=""):
    rows = []
    for page_index, page_id in enumerate(PAGE_IDS):
        for check_id in CHECKS:
            state = "pass"
            if check_id == "search_policy":
                failing_index = 0 if swap_search_policy else 1
                state = "fail" if page_index == failing_index else "pass"
            rows.append(
                Observation(
                    page_id,
                    check_id,
                    state,
                    f"evidence:{page_id}:{check_id}{evidence_suffix}",
                    "",
                )
            )
    return rows


def candidate(rows):
    return build_geo_v8_transport_candidate(
        PAGE_IDS,
        rows,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )


def build_binding(rows, *, candidate_value=None):
    return build_geo_v8_transport_observation_binding(
        candidate_value or candidate(rows),
        PAGE_IDS,
        rows,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )


def test_observation_binding_version_and_exact_population_are_explicit():
    rows = observations()
    binding = build_binding(rows)

    assert VERSION == "geo_v8_transport_observation_binding_v1"
    assert binding["observation_count"] == len(PAGE_IDS) * len(CHECKS)
    assert len(binding["observation_population_fingerprint"]) == 64
    assert binding["candidate"]["authority_verified"] is False
    assert binding["authority_verified"] is False
    assert binding["seal_state"] == "unsealed_candidate"
    assert validate_geo_v8_transport_observation_binding(
        binding,
        PAGE_IDS,
        rows,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    ) is True


def test_self_consistent_candidate_from_different_observations_fails_source_binding():
    trusted = observations()
    forged = list(trusted)
    first = forged[0]
    forged[0] = Observation(first.page_id, first.check_id, "fail", first.evidence_ref, "")
    forged_candidate = candidate(forged)

    # The earlier layers can prove the candidate is internally coherent and has
    # no forged optional sidecars, but they do not know the trusted scored rows.
    assert validate_geo_v8_transport_sources(
        forged_candidate,
        PAGE_IDS,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    ) is True
    with pytest.raises(ValueError, match="exact retained GEO observation population"):
        build_binding(trusted, candidate_value=forged_candidate)


def test_same_aggregate_different_page_allocation_has_distinct_source_identity():
    first = build_binding(observations())
    second = build_binding(observations(swap_search_policy=True))

    assert first["candidate"] == second["candidate"]
    assert first["observation_population_fingerprint"] != second["observation_population_fingerprint"]
    assert serialize_geo_v8_transport_observation_binding(
        first,
        PAGE_IDS,
        observations(),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    ) != serialize_geo_v8_transport_observation_binding(
        second,
        PAGE_IDS,
        observations(swap_search_policy=True),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )


def test_evidence_reference_change_is_bound_even_when_score_is_unchanged():
    first = build_binding(observations())
    changed_rows = observations(evidence_suffix=":changed")
    second = build_binding(changed_rows)

    assert first["candidate"] == second["candidate"]
    assert first["observation_population_fingerprint"] != second["observation_population_fingerprint"]


def test_observation_order_is_non_authoritative():
    rows = observations()
    first = build_binding(rows)
    second = build_binding(list(reversed(rows)), candidate_value=first["candidate"])

    assert first == second


def test_binding_rejects_population_fingerprint_tampering():
    rows = observations()
    binding = build_binding(rows)
    binding["observation_population_fingerprint"] = "f" * 64

    with pytest.raises(ValueError, match="observation binding"):
        validate_geo_v8_transport_observation_binding(
            binding,
            PAGE_IDS,
            rows,
            parent_authoritative=True,
            entry_verified=True,
            access_limited=False,
        )


def test_binding_deep_copies_candidate():
    rows = observations()
    original = candidate(rows)
    binding = build_binding(rows, candidate_value=original)
    original["readiness"]["reasons"].append("caller_mutation")

    assert "caller_mutation" not in binding["candidate"]["readiness"]["reasons"]


def test_reload_identity_requires_exact_observation_bound_bytes():
    rows = observations()
    binding = build_binding(rows)
    expected = serialize_geo_v8_transport_observation_binding(
        binding,
        PAGE_IDS,
        rows,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    reloaded = deepcopy(binding)

    assert validate_geo_v8_transport_observation_binding_reload_identity(
        expected,
        reloaded,
        PAGE_IDS,
        rows,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    ) is True


def test_reload_identity_rejects_different_trusted_observation_population():
    rows = observations()
    binding = build_binding(rows)
    expected = serialize_geo_v8_transport_observation_binding(
        binding,
        PAGE_IDS,
        rows,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )

    with pytest.raises(ValueError):
        validate_geo_v8_transport_observation_binding_reload_identity(
            expected,
            binding,
            PAGE_IDS,
            observations(swap_search_policy=True),
            parent_authoritative=True,
            entry_verified=True,
            access_limited=False,
        )


def test_access_limited_binding_rejects_content_observations():
    candidate_value = build_geo_v8_transport_candidate(
        PAGE_IDS,
        (),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=True,
    )
    with pytest.raises(ValueError, match="Access-limited GEO binding"):
        build_geo_v8_transport_observation_binding(
            candidate_value,
            PAGE_IDS,
            observations(),
            parent_authoritative=True,
            entry_verified=True,
            access_limited=True,
        )


def test_binding_rejects_duplicate_page_check_observations_before_fingerprinting():
    rows = observations()
    with pytest.raises(ValueError, match="Duplicate page/check observation"):
        build_binding(rows + [rows[0]])


def test_binding_rejects_unbounded_observation_metadata_before_fingerprinting():
    rows = observations()
    first = rows[0]
    rows[0] = Observation(
        first.page_id,
        first.check_id,
        first.state,
        "e" * 201,
        first.reason,
    )

    with pytest.raises(ValueError, match="metadata exceeds bounds"):
        build_binding(rows)


def test_binding_rejects_extra_transport_fields_even_with_recomputed_digest():
    rows = observations()
    binding = build_binding(rows)
    binding["invented_authority"] = True

    with pytest.raises(ValueError, match="Malformed GEO V8 observation binding"):
        validate_geo_v8_transport_observation_binding(
            binding,
            PAGE_IDS,
            rows,
            parent_authoritative=True,
            entry_verified=True,
            access_limited=False,
        )


@pytest.mark.parametrize("gate", [1, "true", None])
def test_binding_rejects_type_coerced_gate_facts(gate):
    rows = observations()
    with pytest.raises(ValueError, match="three boolean gate facts"):
        build_geo_v8_transport_observation_binding(
            candidate(rows),
            PAGE_IDS,
            rows,
            parent_authoritative=gate,
            entry_verified=True,
            access_limited=False,
        )
