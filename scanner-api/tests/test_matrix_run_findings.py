"""Two faults a 30-site matrix run surfaced in the numbers a customer reads.

A sitemap index routinely lists other subdomains. `normalize_sitemap_page_url`
deliberately leaves those on their own host -- rewriting them onto the scanned
origin would invent pages that do not exist there -- but nothing downstream
re-checked the host, because `is_same_prefix` compares the path only. Foreign
subdomain URLs therefore entered the discovery inventory and inflated
`pages_found`, while the crawler's strict `same_origin` guard meant they were
never fetched. One site reported roughly 5,000 pages found against 150 crawled,
600 of them belonging to a subdomain that was never in scope.

The second fault is the score. Nineteen findings that were almost entirely
image descriptions and repeated headings produced a 28 on a working lending
site -- a number that reads as a verdict on the business rather than a list of
afternoon jobs, on a page that tells the owner a shorter list is the goal.
"""

import re
from pathlib import Path

from app.review import (
    HEALTH_SCORE_BUCKET_CAPS,
    HEALTH_SCORE_FLOOR,
    compute_health_score_breakdown,
)
from app.sitemap import is_same_prefix, is_scannable_sitemap_url, normalize_sitemap_page_url

ORIGIN = "https://example.com"


def test_a_foreign_subdomain_is_not_counted_as_a_discovered_page():
    blog = "https://blog.example.com/posts/hello"
    # The path check alone accepts it, which is exactly how it got in.
    assert is_same_prefix(blog, "") is True
    assert is_scannable_sitemap_url(blog, ORIGIN) is False


def test_the_scanned_host_and_its_www_alias_are_both_scannable():
    for url in (
        "https://example.com/pricing",
        "https://www.example.com/pricing",
        "http://example.com/pricing",
    ):
        assert is_scannable_sitemap_url(url, ORIGIN) is True, url
    # And the www alias is still rewritten onto the scanned origin, so the
    # crawler's strict same-origin guard accepts it.
    assert normalize_sitemap_page_url("https://www.example.com/pricing", ORIGIN) == "https://example.com/pricing"


def test_a_relative_entry_is_left_to_the_path_check():
    # A sitemap entry with no host carries no competing origin, so rejecting it
    # here would drop real pages. The prefix check remains the arbiter.
    assert is_scannable_sitemap_url("/pricing", ORIGIN) is True
    assert is_scannable_sitemap_url("pricing.html", ORIGIN) is True


def test_a_malformed_entry_is_not_mistaken_for_a_relative_one():
    # These name a scheme or an authority and still parse with no hostname.
    # Treating them as relative let them through the host check and into the
    # discovery inventory, which is the count this guard exists to keep honest.
    for url in ("http://:80/path", "https://", "http://@/x"):
        assert is_scannable_sitemap_url(url, ORIGIN) is False, url


def test_a_subdomain_that_merely_contains_the_scanned_host_is_still_foreign():
    # Guards against a substring match: notexample.com and example.com.evil.tld
    # are different sites.
    assert is_scannable_sitemap_url("https://notexample.com/a", ORIGIN) is False
    assert is_scannable_sitemap_url("https://example.com.evil.tld/a", ORIGIN) is False


def test_discovery_is_unfiltered_when_no_origin_is_known():
    # Without a scanned origin there is nothing to compare against, and silently
    # emptying the inventory would be worse than leaving it to the path check.
    assert is_scannable_sitemap_url("https://blog.example.com/a", "") is True


FINGERPRINT = {
    "pages_crawled": 150,
    "pages_found": 184,
    "pages_received": 150,
    "sampled_pages_sent_to_ai": 150,
}


def _fix(rule, priority, category, count, family="", scope=""):
    return {
        "rule": rule,
        "priority": priority,
        "category": category,
        "page_count": count,
        "affected_pages": [f"/{rule}/{index}" for index in range(count)],
        "page_template_family": family,
        "page_scope": scope,
    }


# The production shape: one real template fault, one canonical gap, and
# seventeen findings that are alt text, headings and descriptions.
COSMETIC_SITE = [
    _fix("broken_location_template_content", "critical", "web_dev", 60, "location_landing"),
    _fix("canonical_missing", "high", "canonical", 12),
    *[_fix("missing_h1", "medium", "thin_content", 4, f"family{n}") for n in range(5)],
    *[_fix("image_alt_text", "low", "image_alt_text", 7, f"images{n}") for n in range(8)],
    _fix("missing_meta_description", "medium", "meta_description", 9, "conversion"),
    _fix("duplicate_title", "medium", "meta_title", 5, "guide_article"),
    _fix("potential_orphan_pages", "low", "internal_link", 4),
]

# A site search engines cannot properly index. Fewer findings, far worse site.
BROKEN_SITE = [
    _fix("canonical_target_noindex", "critical", "canonical", 90, scope="sitewide"),
    _fix("noindex_issue", "critical", "indexability", 80, scope="sitewide"),
    _fix("redirect_chain", "high", "internal_link", 40, scope="sitewide"),
]


def _score(fixes):
    return compute_health_score_breakdown(fixes, FINGERPRINT)["score"]


def test_a_site_whose_only_faults_are_cosmetic_is_not_scored_as_failing():
    score = _score(COSMETIC_SITE)
    assert score >= 55, f"nineteen cosmetic findings scored {score}"
    assert score <= 75, f"cosmetic findings must still cost something: {score}"


def test_broken_indexability_outscores_nothing_and_beats_breadth():
    # The fault this ordering exists to prevent. Under the previous table the
    # cosmetic site scored 53 and the broken one 54: nineteen small findings
    # spread across five buckets out-penalized two catastrophic ones confined
    # to a single bucket, so breadth beat severity and the ranking inverted.
    assert _score(BROKEN_SITE) < _score(COSMETIC_SITE)
    assert _score(BROKEN_SITE) <= 45


def test_the_three_cosmetic_buckets_cannot_sink_a_working_site_between_them():
    cosmetic_total = (
        HEALTH_SCORE_BUCKET_CAPS["search_appearance"]
        + HEALTH_SCORE_BUCKET_CAPS["page_content"]
        + HEALTH_SCORE_BUCKET_CAPS["technical_quality"]
    )
    # The exact documented figure, not a range. Slack here would let the cap
    # drift to 30 while the comment above the table still claimed 28.
    assert cosmetic_total == 28, f"cosmetic buckets can cost {cosmetic_total} points combined"
    # Search visibility must be able to sink a score by itself, or the ordering
    # above is an accident of these particular fixtures.
    assert HEALTH_SCORE_BUCKET_CAPS["search_visibility"] > cosmetic_total


def test_a_clean_scan_still_scores_full_marks():
    assert _score([]) == 100


def test_a_handful_of_medium_findings_is_a_light_deduction():
    # The bucket caps do the work on a site with many findings, so they hide the
    # per-finding weights entirely. This case sits below every cap, which is the
    # only place the severity table is actually visible: under the old weights
    # these same two findings cost 13 points instead of 8.
    small = [
        _fix("missing_h1", "medium", "thin_content", 4, "guide_article"),
        _fix("missing_meta_description", "medium", "meta_description", 5, "conversion"),
    ]
    breakdown = compute_health_score_breakdown(small, FINGERPRINT)
    assert breakdown["total_penalty"] < 10, breakdown["bucket_penalties"]
    assert breakdown["score"] >= 90, f"two fixable findings scored {breakdown['score']}"


def test_alt_text_alone_is_a_small_deduction():
    alt_only = [_fix("image_alt_text", "low", "image_alt_text", 30)]
    assert _score(alt_only) >= 90


def test_a_blocked_crawl_cannot_report_a_healthy_score():
    # A blocked crawl finds few problems precisely because it saw few pages. The
    # ceiling exists so that silence is not rewarded, and it sits above the
    # floor, so it pulls a high score down rather than pushing a low one lower.
    blocked = dict(FINGERPRINT, blocked_access_pages=40, pages_crawled=1, pages_received=1)
    assert compute_health_score_breakdown([], blocked)["score"] <= 45


def test_the_worst_possible_site_lands_exactly_on_the_floor():
    # Without the floor this scores 11. The floor is what stops the number
    # reading as a verdict on the business rather than a list of work, and it
    # has to be exercised by a case that would otherwise fall through it.
    everything = [
        _fix("noindex_issue", "critical", "indexability", 140, scope="sitewide"),
        _fix("canonical_target_noindex", "critical", "canonical", 140, scope="sitewide"),
        _fix("redirect_chain", "critical", "internal_link", 140, scope="sitewide"),
        _fix("potential_orphan_pages", "critical", "internal_link", 140, scope="sitewide"),
        _fix("missing_meta_description", "critical", "meta_description", 140, scope="sitewide"),
        _fix("duplicate_title", "critical", "meta_title", 140, scope="sitewide"),
        _fix("missing_h1", "critical", "thin_content", 140, scope="sitewide"),
        _fix("image_alt_text", "critical", "image_alt_text", 140, scope="sitewide"),
    ]
    breakdown = compute_health_score_breakdown(everything, FINGERPRINT)
    assert breakdown["total_penalty"] > 60, "this fixture must exceed the floor to test it"
    # The literal, not the constant. Comparing the score against
    # HEALTH_SCORE_FLOOR moves both sides together and pins nothing: the floor
    # is a calibration decision, so changing it should have to come here and say
    # so rather than passing silently.
    assert breakdown["score"] == 40
    assert HEALTH_SCORE_FLOOR == 40


def test_the_subdomain_guard_is_applied_where_urls_are_accepted():
    """A predicate nothing calls is not a fix.

    Both acceptance points -- root urlsets and child sitemaps -- have to run the
    host check. Testing `is_scannable_sitemap_url` on its own proves the
    function works, not that discovery uses it, and a guard that exists but is
    never consulted is the exact shape of defect this scan pipeline keeps
    producing.
    """
    source = (Path(__file__).resolve().parents[1] / "app" / "sitemap.py").read_text(encoding="utf-8")
    accepted = re.findall(
        r"if ([^\n]*?)is_same_prefix\(normalized, path_prefix\):\n\s*bucket\.append",
        source,
    )
    assert len(accepted) == 2, f"expected both acceptance points, found {len(accepted)}"
    for guard in accepted:
        assert "is_scannable_sitemap_url(normalized, origin)" in guard, (
            "a sitemap URL is accepted into discovery without checking its host"
        )
