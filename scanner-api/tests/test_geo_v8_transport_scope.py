from copy import deepcopy
from hashlib import sha256

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_readiness_v2 import _scope_digest
from app.geo_v8_transport_candidate import (
    _candidate_digest,
    build_geo_v8_transport_candidate,
    validate_geo_v8_transport_candidate,
)
from app.geo_v8_transport_scope import (
    serialize_geo_v8_transport_candidate_for_scope,
    validate_geo_v8_transport_scope,
)
from app.geo_v8_transport_serialization import serialize_geo_v8_transport_candidate


def rows(page_ids):
    return [
        Observation(page_id, check_id, "pass", "evidence-ref", "")
        for page_id in page_ids
        for check_id in CHECKS
    ]


def build(page_ids=("page-1",), observations=None, **kwargs):
    ids = list(page_ids)
    return build_geo_v8_transport_candidate(
        ids,
        rows(ids) if observations is None else observations,
        parent_authoritative=True,
        entry_verified=True,
        **kwargs,
    )


def opaque(raw):
    return "p_" + sha256(raw.encode()).hexdigest()[:24]


def robots_page(raw):
    return {
        "page_id": raw,
        "robots_txt_rules_known": True,
        "robots_txt_status": "available",
        "robots_txt_status_code": 200,
        "robots_txt_oai_searchbot_allowed": True,
        "robots_txt_gptbot_allowed": True,
        "robots_txt_googlebot_allowed": True,
    }


def redigest(candidate):
    candidate["candidate_digest"] = _candidate_digest(candidate)
    return candidate


def test_scope_bound_serializer_preserves_existing_canonical_bytes():
    candidate = build()
    assert serialize_geo_v8_transport_candidate_for_scope(candidate, ["page-1"]) == serialize_geo_v8_transport_candidate(candidate)


def test_scope_binding_is_order_independent_but_set_exact():
    ids = ["page-a", "page-b"]
    candidate = build(ids)
    assert validate_geo_v8_transport_scope(candidate, list(reversed(ids))) is True
    with pytest.raises(ValueError, match="does not match declared page set"):
        validate_geo_v8_transport_scope(candidate, ["page-a", "page-c"])


def test_collision_safe_scope_rejects_old_newline_join_aliases():
    first = ["a\nb", "c"]
    second = ["a", "b\nc"]
    assert "\n".join(sorted(first)) == "\n".join(sorted(second))
    assert _scope_digest(first) != _scope_digest(second)
    candidate = build(first)
    with pytest.raises(ValueError, match="does not match declared page set"):
        validate_geo_v8_transport_scope(candidate, second)


def test_recomputed_candidate_digest_cannot_rebind_unknown_cell_to_foreign_page():
    candidate = build(observations=[])
    candidate["readiness"]["unknown_cells"][0]["page_id"] = "foreign-page"
    redigest(candidate)
    assert validate_geo_v8_transport_candidate(candidate) is True
    with pytest.raises(ValueError, match="unknown cell is outside"):
        validate_geo_v8_transport_scope(candidate, ["page-1"])


def test_recomputed_candidate_digest_cannot_rebind_named_robot_sidecar_to_foreign_page():
    raw = "https://example.com/"
    page_id = opaque(raw)
    candidate = build((page_id,), robots_pages=[robots_page(raw)])
    candidate["named_robots"][0]["page_id"] = "foreign-page"
    redigest(candidate)
    assert validate_geo_v8_transport_candidate(candidate) is True
    with pytest.raises(ValueError, match="sidecar is outside"):
        validate_geo_v8_transport_scope(candidate, [page_id])


def test_scope_binding_rejects_duplicate_declared_page_ids():
    candidate = build(("page-1",))
    with pytest.raises(ValueError, match="Duplicate declared"):
        validate_geo_v8_transport_scope(candidate, ["page-1", "page-1"])


def test_scope_binding_rejects_malformed_or_oversized_page_ids():
    candidate = build(("page-1",))
    with pytest.raises(ValueError, match="Malformed declared"):
        validate_geo_v8_transport_scope(candidate, [""])
    with pytest.raises(ValueError, match="Malformed declared"):
        validate_geo_v8_transport_scope(candidate, ["x" * 201])
    with pytest.raises(ValueError, match="at most 150"):
        validate_geo_v8_transport_scope(candidate, [f"page-{i}" for i in range(151)])


def test_access_limited_candidate_still_binds_exact_page_set_without_exposing_sidecars():
    candidate = build(("page-1",), access_limited=True)
    assert candidate["readiness"]["assessment_status"] == "access_limited"
    assert candidate["readiness"]["score"] is None
    assert candidate["named_robots"] == []
    assert candidate["llms_txt"] is None
    assert validate_geo_v8_transport_scope(candidate, ["page-1"]) is True


def test_scope_bound_serialization_rejects_digest_invalid_candidate_first():
    candidate = build()
    candidate["candidate_digest"] = "0" * 64
    with pytest.raises(ValueError, match="candidate digest mismatch"):
        serialize_geo_v8_transport_candidate_for_scope(candidate, ["page-1"])


def test_scope_bound_validation_and_serialization_do_not_mutate_inputs():
    ids = ["page-1"]
    candidate = build(ids)
    before_candidate = deepcopy(candidate)
    before_ids = deepcopy(ids)
    validate_geo_v8_transport_scope(candidate, ids)
    serialize_geo_v8_transport_candidate_for_scope(candidate, ids)
    assert candidate == before_candidate
    assert ids == before_ids
