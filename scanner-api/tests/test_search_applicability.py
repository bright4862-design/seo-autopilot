"""Search intent gates metadata, without suppressing visitor-facing evidence."""

from copy import deepcopy
import importlib

import pytest

from app.extract import extract_page
from app.indexability_quality import annotate_indexability_quality


def _api():
    return importlib.import_module("app.search_applicability")


def _page(path="/page", *, head="", sources=None, status=200, headers=None):
    url = f"https://example.com{path}"
    return extract_page(
        f"<html><head><title>Useful page</title>{head}</head>"
        "<body><main><p>Customer content.</p><img src='/hero.jpg'></main></body></html>",
        url, url, status, "text/html",
        {"discovered_from": sources or ["internal_link"], "source_pages": ["/"], "link_text_samples": []},
        response_headers=headers,
    )


def _noindex(path="/page", **kwargs):
    return _page(path, head='<meta name="robots" content="noindex">', **kwargs)


def _canonical(path="/variant", *, target_state="valid"):
    page = _page(path, head='<link rel="canonical" href="https://example.com/preferred">')
    page.update(canonical_target_state=target_state, canonical_target_url="https://example.com/preferred")
    return page


def test_repeated_canonical_annotation_preserves_validated_evidence():
    page = _canonical()
    annotate_indexability_quality(page)
    once = deepcopy(page)

    annotate_indexability_quality(page)

    assert page == once
    assert page["canonicalized_by_valid_target"] is True
    assert page["indexability_state_before_quality"] == "Indexable"


def test_repeated_soft404_annotation_preserves_pre_quality_state():
    page = _page()
    page.update(title="404 Page Not Found", h1="Page not found", word_count=5)
    annotate_indexability_quality(page)
    once = deepcopy(page)

    annotate_indexability_quality(page)

    assert page == once
    assert page["indexability_state"] == "Soft 404"


def test_utility_noindex_excludes_search_metadata_without_mutating_page():
    api = _api()
    page = _noindex("/login")
    page.update(geo_scope="intentional_utility", geo_scope_reason="Owner declares a sign-in page")
    original = deepcopy(page)

    decision = api.search_applicability(page)

    assert decision["version"] == api.SEARCH_APPLICABILITY_VERSION
    assert decision["state"] == "not_applicable"
    assert decision["reason"] == "intentional_utility_noindex"
    assert decision["accepted_html"] is True
    assert decision["search_metadata_applicable"] is False
    assert decision["index_or_drop"] is False
    assert page == original
    for rule in ("missing_title", "missing_meta_description", "canonical_missing", "duplicate_title_template"):
        assert api.rule_is_applicable(page, rule) is False
    for rule in ("image_alt_text", "missing_image_alt", "missing_h1", "multiple_h1", "canonical_target_failed", "failed_page"):
        assert api.rule_is_applicable(page, rule) is True


@pytest.mark.parametrize("sources,declared,expected", [
    (["sitemap"], False, ["sitemap"]),
    (["internal_link"], True, ["declared_search_intent"]),
    (["sitemap"], True, ["sitemap", "declared_search_intent"]),
])
def test_noindex_conflict_produces_one_decision_before_metadata(sources, declared, expected):
    api = _api()
    page = _noindex(sources=sources)
    page.update(geo_scope="intentional_utility", geo_scope_reason="Owner utility declaration", geo_search_intent=declared)

    decision = api.search_applicability(page)

    assert decision["state"] == "not_applicable"
    assert decision["reason"] == "noindex_search_intent_conflict"
    assert decision["index_or_drop"] is True
    assert decision["intent_sources"] == expected
    assert api.search_metadata_applicable(page) is False
    assert api.rule_is_applicable(page, "image_alt_text") is True


def test_unresolved_noindex_intent_is_not_an_indexing_failure():
    decision = _api().search_applicability(_noindex())
    assert decision["state"] == "not_applicable"
    assert decision["reason"] == "noindex_intent_unresolved"
    assert decision["index_or_drop"] is False
    assert decision["search_metadata_applicable"] is False


@pytest.mark.parametrize("head,headers", [
    ('<meta name="googlebot" content="noindex">', None),
    ('<meta name="robots" content="none">', None),
    ("", {"x-robots-tag": "noindex"}),
])
def test_effective_directives_cover_robot_sources_and_none(head, headers):
    page = _page(head=head, headers=headers, sources=["sitemap"])
    assert _api().search_applicability(page)["index_or_drop"] is True
    assert _api().search_metadata_applicable(page) is False


@pytest.mark.parametrize("target_state", ["valid", "canonical_chain"])
def test_validated_canonical_variant_is_excluded_before_or_after_annotation(target_state):
    api = _api()
    page = _canonical(target_state=target_state)

    before = api.search_applicability(page)
    annotate_indexability_quality(page)
    after = api.search_applicability(page)

    assert before == after
    assert after["reason"] == "validated_canonical_away"
    assert after["search_metadata_applicable"] is False
    assert after["index_or_drop"] is False
    assert api.rule_is_applicable(page, "image_alt_text") is True


@pytest.mark.parametrize("target_state", ["", "target_failed", "target_noindex", "target_blocked_by_robots", "cross_domain_needs_verification"])
def test_raw_or_unverified_canonical_does_not_hide_independent_metadata(target_state):
    page = _canonical(target_state=target_state)
    assert _api().search_metadata_applicable(page) is True


def test_retained_validated_stamp_works_without_target_details_but_not_against_failure():
    page = _canonical()
    page.update(canonicalized_by_valid_target=True)
    page.pop("canonical_target_state")
    assert _api().search_metadata_applicable(page) is False
    page["canonical_target_state"] = "target_failed"
    assert _api().search_metadata_applicable(page) is True


@pytest.mark.parametrize("status,headers", [
    (202, {"sg-captcha": "challenge", "x-robots-tag": "noindex"}),
    (200, {"cf-mitigated": "challenge", "x-robots-tag": "noindex"}),
    (403, {"x-robots-tag": "noindex"}),
    (429, {"x-robots-tag": "noindex"}),
])
def test_challenge_or_failed_access_never_supports_index_or_drop(status, headers):
    page = _page(status=status, headers=headers, sources=["sitemap"])
    page["geo_search_intent"] = True
    decision = _api().search_applicability(page)
    assert decision["state"] == "not_verified"
    assert decision["accepted_html"] is False
    assert decision["search_metadata_applicable"] is False
    assert decision["index_or_drop"] is False


def test_mixed_published_routes_remain_distinct_and_filter_individually():
    api = _api()
    pages = [_page("/x"), _noindex("/x/"), _page("/X")]
    decisions = {page["url"]: api.search_applicability(page) for page in pages}
    assert len(decisions) == 3
    assert [url for url, decision in decisions.items() if decision["search_metadata_applicable"]] == [
        "https://example.com/x", "https://example.com/X",
    ]
    assert all(api.rule_is_applicable(page, "image_alt_text") for page in pages)


def test_utility_path_alone_does_not_prove_search_exclusion():
    page = _page("/login")
    assert _api().search_metadata_applicable(page) is True


def test_missing_directives_can_use_retained_noindex_state():
    page = _noindex()
    page.pop("effective_search_robots_directives")
    assert _api().search_metadata_applicable(page) is False


def test_malformed_directives_are_unknown_not_a_conflict():
    page = _page(sources=["sitemap"])
    page["effective_search_robots_directives"] = "noindex"
    decision = _api().search_applicability(page)
    assert decision["state"] == "not_verified"
    assert decision["index_or_drop"] is False


def test_search_rule_allowlist_does_not_expand_to_unrelated_rules():
    api = _api()
    page = _noindex()
    assert api.rule_is_applicable(page, "robots_directive_conflict") is True
    assert api.rule_is_applicable(page, "sitemap_indexability_conflict") is True
    assert api.rule_is_applicable(page, "broken_visible_template_content") is True
    assert api.rule_is_applicable(page, "schema_agreement") is True
