from copy import deepcopy

import pytest

from app.geo_evidence import assess_geo_pages, extract_geo_evidence
from app.geo_robots_evidence import VERSION, extract_named_robots_evidence


def page(**overrides):
    value = {
        "url": "https://example.com/page",
        "robots_txt_status": "available",
        "robots_txt_status_code": 200,
        "robots_txt_rules_known": True,
        "robots_txt_oai_searchbot_allowed": True,
        "robots_txt_googlebot_allowed": True,
    }
    value.update(overrides)
    return value


def by_id(result):
    return {row["crawler_id"]: row for row in result["bots"]}


def test_exact_named_crawler_decisions_are_neutral_observed_evidence():
    result = extract_named_robots_evidence(page(
        robots_txt_oai_searchbot_allowed=True,
        robots_txt_googlebot_allowed=False,
        robots_txt_gptbot_allowed=False,
    ))
    assert result["version"] == VERSION
    bots = by_id(result)
    assert bots["oai_searchbot"]["directive"] == "allow"
    assert bots["googlebot"]["directive"] == "disallow"
    assert bots["gptbot"]["directive"] == "disallow"
    assert {row["state"] for row in bots.values()} == {"observed"}
    assert bots["gptbot"]["purpose"] == "training"
    assert "visibility" in result["claim_boundary"]


def test_missing_gptbot_observation_stays_unknown_instead_of_inheriting_oai_policy():
    bots = by_id(extract_named_robots_evidence(page()))
    assert bots["oai_searchbot"]["state"] == "observed"
    assert bots["gptbot"]["state"] == "not_verified"
    assert bots["gptbot"]["directive"] is None
    assert bots["gptbot"]["evidence_ref"] == ""


def test_rules_unknown_keeps_all_named_crawlers_unverified():
    result = extract_named_robots_evidence({
        "url": "https://example.com/page",
        "robots_txt_status": "access_limited",
        "robots_txt_status_code": 403,
        "robots_txt_rules_known": False,
    })
    assert result["rules_known"] is False
    assert {row["state"] for row in result["bots"]} == {"not_verified"}


def test_missing_robots_file_can_report_only_explicit_retained_agent_evaluations():
    bots = by_id(extract_named_robots_evidence(page(
        robots_txt_status="missing",
        robots_txt_status_code=404,
        robots_txt_oai_searchbot_allowed=True,
        robots_txt_googlebot_allowed=True,
    )))
    assert bots["oai_searchbot"]["directive"] == "allow"
    assert bots["googlebot"]["directive"] == "allow"
    assert bots["gptbot"]["state"] == "not_verified"


@pytest.mark.parametrize("field", [
    "robots_txt_oai_searchbot_allowed",
    "robots_txt_googlebot_allowed",
    "robots_txt_gptbot_allowed",
])
def test_malformed_named_crawler_values_fail_closed(field):
    with pytest.raises(ValueError, match="Malformed"):
        extract_named_robots_evidence(page(**{field: "allow"}))


def test_retained_boolean_is_rejected_when_rules_are_not_known():
    with pytest.raises(ValueError, match="Unverified OAI-SearchBot"):
        extract_named_robots_evidence({
            "url": "https://example.com/page",
            "robots_txt_status": "access_limited",
            "robots_txt_status_code": 403,
            "robots_txt_rules_known": False,
            "robots_txt_oai_searchbot_allowed": True,
        })


@pytest.mark.parametrize("status,rules_known", [
    ("available", False),
    ("missing", False),
    ("unavailable", True),
    ("access_limited", True),
])
def test_status_and_rules_known_contradictions_fail_closed(status, rules_known):
    with pytest.raises(ValueError, match="contradicts"):
        extract_named_robots_evidence({
            "url": "https://example.com/page",
            "robots_txt_status": status,
            "robots_txt_rules_known": rules_known,
        })


def test_adapter_is_deterministic_ordered_and_does_not_mutate_page():
    value = page(robots_txt_gptbot_allowed=False, robots_txt_owner_override_applied=True)
    original = deepcopy(value)
    first = extract_named_robots_evidence(value)
    second = extract_named_robots_evidence(value)
    assert first == second
    assert [row["crawler_id"] for row in first["bots"]] == ["oai_searchbot", "gptbot", "googlebot"]
    assert value == original
    assert "owner_override" not in str(first)


def _geo_page(html, url="https://example.com/"):
    value = {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "canonical_status": "self_or_equivalent",
        "effective_search_robots_directives": [],
        "discovered_from": ["internal_link"],
        "source_pages": ["https://example.com/about"],
        "robots_txt_rules_known": True,
        "robots_txt_oai_searchbot_allowed": True,
    }
    value["geo_evidence"] = extract_geo_evidence(html, value)
    return value


def test_untyped_page_bound_jsonld_preserves_existing_schema_agreement_compatibility():
    html = '''<html><title>Acme</title><main><h1>Acme</h1>
    <section itemscope itemtype="https://schema.org/Organization"><span itemprop="name">Acme</span><address itemprop="address">10 Main Street</address></section>
    <article><a rel="author" href="https://example.com/author">A. Writer</a>
    <time itemprop="datePublished" datetime="1998-01-01">January 1, 1998</time>
    <blockquote cite="https://example.org/source">Quoted material</blockquote><a href="https://example.org/source">Source</a></article></main>
    <script type="application/ld+json">{"url":"https://example.com/","name":"Acme"}</script></html>'''
    result = assess_geo_pages([_geo_page(html)], parent_authoritative=True, entry_verified=True)
    states = {row["check_id"]: row["state"] for row in result["observations"]}
    assert states["schema_agreement"] == "pass"
    assert result["assessment_status"] == "assessed"
    assert result["score"] == 100 and result["coverage"] == 1


def test_untyped_page_bound_jsonld_does_not_invent_subject_identity():
    html = '''<html><head><title>Acme</title><script type="application/ld+json">{"url":"https://example.com/","name":"Acme"}</script></head>
    <body><main><h1>Acme</h1><p>About Acme.</p></main></body></html>'''
    result = assess_geo_pages([_geo_page(html)])
    states = {row["check_id"]: row["state"] for row in result["observations"]}
    assert states["schema_agreement"] == "pass"
    assert states["subject_identity"] == "not_verified"
