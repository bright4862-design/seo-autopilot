"""An uncrawled affected URL is a gap in family evidence, not a competing family.

`normalize_repair_scope` stamps each affected URL's family by looking it up in
the crawled page evidence, then requires total agreement. A URL the crawl never
recorded as a page of its own fell to UNKNOWN_FAMILY, and because the scope
rules treat an unaccounted URL as another family, ONE of them collapsed an
otherwise uniform group to `mixed`:

    119 stamped location_landing + 1 uncrawled  ->  scope=mixed, family=mixed

Redirect *destinations* are the common uncrawled case, which is why
redirect_destination_noindex was hit hardest -- the same rule behind the Ike
duplicate-card incident. `mixed` is not cosmetic: it disables sitewide collapse
(review.SITEWIDE_COLLAPSE_RULES), drops `comparable_family` in priority
calibration, lands in NON_SPECIFIC_FAMILIES, and leaves the customer a card that
cannot say what it is about.

Gap-fill is gated on corroboration. It only runs for a repair that already
carries at least one stamped family, and it never overrides a stamp. A repair
the crawl said nothing about keeps `mixed`, because naming a family from paths
alone would be the invented second opinion this pass exists to prevent.

test_repair_scope_partitions.py covers the same function with NO resolver
injected, which is not how production calls it -- see
test_production_callers_inject_a_family_resolver below.
"""
from pathlib import Path

from app.repair_coverage import UNKNOWN_FAMILY, normalize_repair_scope
from app.review import normalize_template_family

SCANNER_APP = Path(__file__).resolve().parents[1] / "app"
LOCATIONS = [f"https://ike.com/menu/location/{i}" for i in range(120)]


def crawled(urls, family="location_landing"):
    return [
        {"final_url": u, "url": u, "path": u, "status_code": 200, "page_template_family": family}
        for u in urls
    ]


def scope(fix, pages, resolver=normalize_template_family):
    return normalize_repair_scope(dict(fix), pages, family_resolver=resolver)


REDIRECT_FIX = {"rule": "redirect_destination_noindex", "affected_pages": LOCATIONS}


def test_one_uncrawled_url_no_longer_collapses_a_uniform_family():
    """The Ike shape: the redirect destination was never crawled as a page."""
    result = scope(REDIRECT_FIX, crawled(LOCATIONS[:-1]))

    assert result["page_scope"] == "family"
    assert result["page_template_family"] == "location_landing"
    assert result["family_breakdown"] == {"location_landing": 120}


def test_gap_fill_scales_to_many_uncrawled_urls():
    result = scope(REDIRECT_FIX, crawled(LOCATIONS[:60]))

    assert result["page_scope"] == "family"
    assert result["family_breakdown"] == {"location_landing": 120}


def test_a_repair_with_no_stamped_family_stays_mixed():
    """Nothing to corroborate: naming a family here would be invented.

    These paths classify cleanly on their own, so this is exactly the case where
    an ungated gap-fill would assert a family with zero page evidence behind it.
    """
    unknown_only = {
        "rule": "missing_h1",
        "affected_pages": [f"https://ike.com/menu/location/{i}" for i in range(22)],
    }

    result = scope(unknown_only, [])

    assert result["page_scope"] == "mixed"
    assert result["page_template_family"] == "mixed"
    assert result["family_breakdown"] == {UNKNOWN_FAMILY: 22}


def test_a_stamped_family_is_never_overridden_by_the_path():
    """The crawl's opinion wins wherever it has one."""
    fix = {"rule": "missing_h1", "affected_pages": ["https://ike.com/looks-like-a-blog-post"]}
    pages = crawled(["https://ike.com/looks-like-a-blog-post"], family="product_page")

    assert scope(fix, pages)["page_template_family"] == "product_page"


def test_genuinely_different_families_still_read_mixed():
    """Gap-fill must not flatten a real partition."""
    fix = {
        "rule": "missing_h1",
        "affected_pages": ["https://ike.com/menu/location/a", "https://ike.com/blog/x", "https://ike.com/checkout/y"],
    }
    pages = (
        crawled(["https://ike.com/menu/location/a"], family="location_landing")
        + crawled(["https://ike.com/blog/x"], family="guide_article")
        + crawled(["https://ike.com/checkout/y"], family="route_boundary")
    )

    result = scope(fix, pages)

    assert result["page_scope"] == "mixed"
    assert result["page_template_family"] == "mixed"
    assert len(result["family_breakdown"]) == 3


def test_a_gap_that_is_a_different_family_still_reads_mixed():
    """Corroboration fills the gap; it does not force agreement."""
    fix = {
        "rule": "missing_h1",
        "affected_pages": ["https://ike.com/menu/location/a", "https://ike.com/blog/never-crawled"],
    }
    pages = crawled(["https://ike.com/menu/location/a"], family="location_landing")

    result = scope(fix, pages)

    assert result["page_scope"] == "mixed"
    assert set(result["family_breakdown"]) == {"location_landing", "guide_article"}


def test_without_a_resolver_the_behaviour_is_unchanged():
    """Callers that inject nothing keep the previous unknown partition."""
    result = scope(REDIRECT_FIX, crawled(LOCATIONS[:-1]), resolver=None)

    assert result["page_scope"] == "mixed"
    assert result["family_breakdown"] == {"location_landing": 119, UNKNOWN_FAMILY: 1}


def test_a_resolver_that_fails_on_the_gap_falls_back_to_unknown():
    """A fault while filling a gap degrades to the old answer, not a crash.

    Only the gap-fill call is exercised: the resolver behaves normally for
    stamped pages, and raises on the `stamped is None` invocation this pass
    added. (The pre-existing `_page_family` call site is unguarded, so a
    resolver that raised for everything would fail before reaching here.)
    """
    def boom_on_gap(stamped, url):
        if stamped is None:
            raise RuntimeError("resolver unavailable")
        return normalize_template_family(stamped, url)

    result = scope(REDIRECT_FIX, crawled(LOCATIONS[:-1]), resolver=boom_on_gap)

    assert result["family_breakdown"] == {"location_landing": 119, UNKNOWN_FAMILY: 1}


def test_production_callers_inject_a_family_resolver():
    """Guards against this contract going vacuous again.

    Every existing assertion in test_repair_scope_partitions.py calls
    normalize_repair_scope with no resolver, while both production callers pass
    one -- so that file describes a configuration production never runs. These
    tests cover the injected path; this one keeps the two in step.
    """
    for module in ("review.py", "repair_contract_v2.py"):
        source = (SCANNER_APP / module).read_text(encoding="utf-8")
        assert "normalize_repair_scope(" in source, module
        assert "family_resolver=normalize_template_family" in source, module
