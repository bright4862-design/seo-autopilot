from copy import deepcopy
from hashlib import sha256

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_transport_candidate import (
    _candidate_digest,
    build_geo_v8_transport_candidate,
    validate_geo_v8_transport_candidate,
)
from app.geo_v8_transport_serialization import serialize_geo_v8_transport_candidate
from app.geo_v8_transport_sources import (
    serialize_geo_v8_transport_candidate_for_sources,
    validate_geo_v8_transport_sources,
)


def opaque(raw):
    return "p_" + sha256(raw.encode()).hexdigest()[:24]


def rows(page_ids, state="pass"):
    evidence = "evidence-ref" if state in {"pass", "fail"} else ""
    reason = "fixture N/A" if state == "not_applicable" else ""
    return [
        Observation(page_id, check_id, state, evidence, reason)
        for page_id in page_ids
        for check_id in CHECKS
    ]


def robots_page(raw):
    return {
        "page_id": raw,
        "robots_txt_rules_known": True,
        "robots_txt_status": "available",
        "robots_txt_status_code": 200,
        "robots_txt_oai_searchbot_allowed": True,
        "robots_txt_gptbot_allowed": False,
        "robots_txt_googlebot_allowed": True,
    }


def llms_observation():
    return {
        "url": "https://example.com/llms.txt",
        "status_code": 200,
        "content_type": "text/plain",
        "body": "# Example\n\n> Structural guide\n\n## Docs\n- [Guide](/guide)\n",
    }


def build_with_sources(*, access_limited=False, include_robots=True, include_llms=True):
    raw = "https://example.com/product/1"
    page_id = opaque(raw)
    robot_sources = [robots_page(raw)] if include_robots else []
    llms_source = llms_observation() if include_llms else None
    candidate = build_geo_v8_transport_candidate(
        [page_id],
        rows([page_id]),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=access_limited,
        robots_pages=robot_sources,
        llms_txt_observation=llms_source,
    )
    return candidate, [page_id], robot_sources, llms_source


def validate(candidate, page_ids, robot_sources, llms_source, *, access_limited=False):
    return validate_geo_v8_transport_sources(
        candidate,
        page_ids,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=access_limited,
        robots_pages=robot_sources,
        llms_txt_observation=llms_source,
    )


def redigest(candidate):
    candidate["candidate_digest"] = _candidate_digest(candidate)
    return candidate


def test_exact_retained_sources_bind_and_preserve_canonical_candidate_bytes():
    candidate, page_ids, robot_sources, llms_source = build_with_sources()
    assert validate(candidate, page_ids, robot_sources, llms_source) is True
    assert serialize_geo_v8_transport_candidate_for_sources(
        candidate,
        page_ids,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
        robots_pages=robot_sources,
        llms_txt_observation=llms_source,
    ) == serialize_geo_v8_transport_candidate(candidate)


def test_recomputed_digest_cannot_forge_named_crawler_directive():
    candidate, page_ids, robot_sources, llms_source = build_with_sources()
    bot = next(
        item for item in candidate["named_robots"][0]["bots"]
        if item["crawler_id"] == "gptbot"
    )
    assert bot["directive"] == "disallow"
    bot["directive"] = "allow"
    redigest(candidate)

    assert validate_geo_v8_transport_candidate(candidate) is True
    with pytest.raises(ValueError, match="Named-crawler GEO sidecars"):
        validate(candidate, page_ids, robot_sources, llms_source)


def test_recomputed_digest_cannot_forge_llms_structural_count():
    candidate, page_ids, robot_sources, llms_source = build_with_sources()
    candidate["llms_txt"]["linked_resource_count"] += 1
    redigest(candidate)

    assert validate_geo_v8_transport_candidate(candidate) is True
    with pytest.raises(ValueError, match="llms.txt GEO sidecar"):
        validate(candidate, page_ids, robot_sources, llms_source)


def test_missing_retained_robots_source_cannot_authorize_existing_sidecar():
    candidate, page_ids, _, llms_source = build_with_sources()
    with pytest.raises(ValueError, match="Named-crawler GEO sidecars"):
        validate(candidate, page_ids, [], llms_source)


def test_extra_retained_robots_source_cannot_authorize_absent_sidecar():
    candidate, page_ids, robot_sources, llms_source = build_with_sources(
        include_robots=False
    )
    extra = [robots_page("https://example.com/product/1")]
    with pytest.raises(ValueError, match="Named-crawler GEO sidecars"):
        validate(candidate, page_ids, extra, llms_source)
    assert robot_sources == []


def test_missing_retained_llms_source_cannot_authorize_existing_sidecar():
    candidate, page_ids, robot_sources, _ = build_with_sources()
    with pytest.raises(ValueError, match="llms.txt GEO sidecar"):
        validate(candidate, page_ids, robot_sources, None)


def test_extra_retained_llms_source_cannot_authorize_absent_sidecar():
    candidate, page_ids, robot_sources, _ = build_with_sources(
        include_llms=False
    )
    with pytest.raises(ValueError, match="llms.txt GEO sidecar"):
        validate(candidate, page_ids, robot_sources, llms_observation())


def test_access_limited_source_binding_accepts_no_optional_sources():
    candidate, page_ids, _, _ = build_with_sources(access_limited=True)
    assert validate(
        candidate,
        page_ids,
        [],
        None,
        access_limited=True,
    ) is True


def test_access_limited_source_binding_rejects_optional_source_observations():
    candidate, page_ids, _, _ = build_with_sources(access_limited=True)
    with pytest.raises(ValueError, match="Access-limited GEO source binding"):
        validate(
            candidate,
            page_ids,
            [robots_page("https://example.com/product/1")],
            None,
            access_limited=True,
        )


def test_source_binding_does_not_mutate_candidate_or_retained_inputs():
    candidate, page_ids, robot_sources, llms_source = build_with_sources()
    candidate_before = deepcopy(candidate)
    robots_before = deepcopy(robot_sources)
    llms_before = deepcopy(llms_source)

    validate(candidate, page_ids, robot_sources, llms_source)

    assert candidate == candidate_before
    assert robot_sources == robots_before
    assert llms_source == llms_before


def test_retained_robots_source_order_is_non_authoritative():
    raw_one = "https://example.com/product/1"
    raw_two = "https://example.com/product/2"
    page_ids = [opaque(raw_one), opaque(raw_two)]
    robot_sources = [robots_page(raw_one), robots_page(raw_two)]
    candidate = build_geo_v8_transport_candidate(
        page_ids,
        rows(page_ids),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
        robots_pages=robot_sources,
        llms_txt_observation=None,
    )
    expected_bytes = serialize_geo_v8_transport_candidate(candidate)

    assert validate(candidate, page_ids, list(reversed(robot_sources)), None) is True
    assert serialize_geo_v8_transport_candidate_for_sources(
        candidate,
        page_ids,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
        robots_pages=list(reversed(robot_sources)),
        llms_txt_observation=None,
    ) == expected_bytes


def test_duplicate_retained_robots_source_identity_is_rejected():
    candidate, page_ids, robot_sources, llms_source = build_with_sources()
    duplicate = [robot_sources[0], deepcopy(robot_sources[0])]

    with pytest.raises(ValueError, match="Duplicate retained robots source identity"):
        validate(candidate, page_ids, duplicate, llms_source)


def test_conflicting_duplicate_retained_robots_source_identity_is_rejected():
    candidate, page_ids, robot_sources, llms_source = build_with_sources()
    conflicting = deepcopy(robot_sources[0])
    conflicting["robots_txt_gptbot_allowed"] = True

    with pytest.raises(ValueError, match="Duplicate retained robots source identity"):
        validate(candidate, page_ids, [robot_sources[0], conflicting], llms_source)
