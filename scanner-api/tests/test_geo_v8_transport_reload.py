from copy import deepcopy
from hashlib import sha256

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_transport_candidate import _candidate_digest, build_geo_v8_transport_candidate
from app.geo_v8_transport_reload import validate_geo_v8_transport_reload_identity
from app.geo_v8_transport_sources import serialize_geo_v8_transport_candidate_for_sources


def opaque(raw):
    return "p_" + sha256(raw.encode()).hexdigest()[:24]


def rows(page_ids, *, unknown=False):
    result = [
        Observation(page_id, check_id, "pass", "evidence-ref", "")
        for page_id in page_ids
        for check_id in CHECKS
    ]
    if unknown:
        first = result[0]
        result[0] = Observation(
            first.page_id,
            first.check_id,
            "not_verified",
            "",
            "fixture uncertainty",
        )
    return result


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


def build_fixture(*, access_limited=False, unknown=False, two_pages=False):
    raws = ["https://example.com/product/1"]
    if two_pages:
        raws.append("https://example.com/product/2")
    page_ids = [opaque(raw) for raw in raws]
    robot_sources = [] if access_limited else [robots_page(raw) for raw in raws]
    llms_source = None if access_limited else llms_observation()
    candidate = build_geo_v8_transport_candidate(
        page_ids,
        rows(page_ids, unknown=unknown),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=access_limited,
        robots_pages=robot_sources,
        llms_txt_observation=llms_source,
    )
    expected = serialize_geo_v8_transport_candidate_for_sources(
        candidate,
        page_ids,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=access_limited,
        robots_pages=robot_sources,
        llms_txt_observation=llms_source,
    )
    return candidate, page_ids, robot_sources, llms_source, expected


def validate(candidate, page_ids, robot_sources, llms_source, expected, *, access_limited=False):
    return validate_geo_v8_transport_reload_identity(
        expected,
        candidate,
        page_ids,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=access_limited,
        robots_pages=robot_sources,
        llms_txt_observation=llms_source,
    )


def test_exact_source_bound_candidate_survives_reload_identity_check():
    candidate, page_ids, robot_sources, llms_source, expected = build_fixture()
    assert validate(candidate, page_ids, robot_sources, llms_source, expected) is True


def test_mapping_insertion_order_is_not_reload_identity():
    candidate, page_ids, robot_sources, llms_source, expected = build_fixture()
    reordered = {key: candidate[key] for key in reversed(tuple(candidate))}
    assert validate(reordered, page_ids, robot_sources, llms_source, expected) is True


def test_retained_source_order_is_not_reload_identity():
    candidate, page_ids, robot_sources, llms_source, expected = build_fixture(two_pages=True)
    assert validate(
        candidate,
        page_ids,
        list(reversed(robot_sources)),
        llms_source,
        expected,
    ) is True


def test_different_expected_preseal_bytes_fail_closed():
    candidate, page_ids, robot_sources, llms_source, expected = build_fixture()
    wrong = expected[:-1] + (b"0" if expected[-1:] != b"0" else b"1")
    with pytest.raises(ValueError, match="differ from pre-seal identity"):
        validate(candidate, page_ids, robot_sources, llms_source, wrong)


def test_redigested_semantically_valid_unknown_reason_cannot_change_reload_identity():
    candidate, page_ids, robot_sources, llms_source, expected = build_fixture(unknown=True)
    changed = deepcopy(candidate)
    assert changed["readiness"]["unknown_cells"]
    changed["readiness"]["unknown_cells"][0]["reason"] = "different retained uncertainty"
    changed["candidate_digest"] = _candidate_digest(changed)

    with pytest.raises(ValueError):
        validate(changed, page_ids, robot_sources, llms_source, expected)


def test_redigested_sidecar_tamper_is_rejected_by_source_rebinding_before_identity():
    candidate, page_ids, robot_sources, llms_source, expected = build_fixture()
    changed = deepcopy(candidate)
    changed["named_robots"][0]["bots"][0]["directive"] = "disallow"
    changed["candidate_digest"] = _candidate_digest(changed)

    with pytest.raises(ValueError, match="Named-crawler GEO sidecars"):
        validate(changed, page_ids, robot_sources, llms_source, expected)


@pytest.mark.parametrize("bad", [None, "", b"", bytearray(b"x")])
def test_expected_preseal_identity_must_be_non_empty_bytes(bad):
    candidate, page_ids, robot_sources, llms_source, _ = build_fixture()
    with pytest.raises(ValueError, match="non-empty canonical GEO pre-seal bytes"):
        validate_geo_v8_transport_reload_identity(
            bad,
            candidate,
            page_ids,
            parent_authoritative=True,
            entry_verified=True,
            access_limited=False,
            robots_pages=robot_sources,
            llms_txt_observation=llms_source,
        )


def test_access_limited_candidate_survives_reload_without_optional_sources():
    candidate, page_ids, _, _, expected = build_fixture(access_limited=True)
    assert validate(
        candidate,
        page_ids,
        [],
        None,
        expected,
        access_limited=True,
    ) is True


def test_access_limited_reload_rejects_optional_sources():
    candidate, page_ids, _, _, expected = build_fixture(access_limited=True)
    with pytest.raises(ValueError, match="Access-limited GEO source binding"):
        validate(
            candidate,
            page_ids,
            [robots_page("https://example.com/product/1")],
            None,
            expected,
            access_limited=True,
        )


def test_reload_identity_check_does_not_mutate_inputs():
    candidate, page_ids, robot_sources, llms_source, expected = build_fixture()
    before = (
        deepcopy(candidate),
        deepcopy(page_ids),
        deepcopy(robot_sources),
        deepcopy(llms_source),
    )

    assert validate(candidate, page_ids, robot_sources, llms_source, expected) is True
    assert candidate == before[0]
    assert page_ids == before[1]
    assert robot_sources == before[2]
    assert llms_source == before[3]
