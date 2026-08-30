"""Ike regression: one redirect_destination_noindex family card must not ship
alongside per-page cards for URLs that card already lists.

Production evidence (scan 6a9459670098c388abf69820, FixList 6a9459aaa1213a7f4fb798c3,
authoritative: 167 found / 150 crawled, release_gate_eligible=true): the rule was
persisted once as a mixed/group card covering 100+ /menu/location/* pages and then
again as ~27 page-scope rows over the same URLs, inflating total_fixes to 34 and
showing the customer many copies of one action.

The seam is `scanner.group_findings()`, which builds the family card by copying a
member finding and blanking `page_url` but never stamps a generator source -- so
`suppress_group_covered_singletons()` did not recognise it as authoritative.
"""

from app.repair_contract_v2 import apply_canonical_repair_contract
from app.review import (
    GROUP_CARD_MIN_AFFECTED,
    fix_dedup_class,
    run_review,
    suppress_group_covered_singletons,
)
from app.scanner import GROUP_MIN_AFFECTED

RULE = "redirect_destination_noindex"
GROUP_PAGES = [f"https://ike.com/menu/location/{i}" for i in range(120)]
# The rows the scanner also emitted per page, all inside the group's page list.
OVERLAPPING = GROUP_PAGES[:27]


def _group_card(pages=None):
    """Shaped like scanner.group_findings() output: blank page_url, pages listed."""
    covered = list(GROUP_PAGES if pages is None else pages)
    return {
        "rule": RULE,
        "category": "indexability",
        "title": "Fix redirects pointing at noindexed pages",
        "issue_title": "Fix redirects pointing at noindexed pages",
        "page_url": "",
        "affected_pages": covered,
        "page_count": len(covered),
        "priority": "high",
        "page_template_family": "mixed",
    }


def _page_row(url, rule=RULE):
    return {
        "rule": rule,
        "category": "indexability",
        "title": "Fix a redirect to a noindexed destination",
        "issue_title": "Fix a redirect to a noindexed destination",
        "page_url": url,
        "affected_pages": [url],
        "page_count": 1,
        "priority": "high",
    }


def test_review_group_threshold_matches_scanner():
    """review.py restates the scanner threshold; drift would silently re-open this bug."""
    assert GROUP_CARD_MIN_AFFECTED == GROUP_MIN_AFFECTED


def test_family_card_suppresses_overlapping_page_rows():
    fixes = [_group_card()] + [_page_row(url) for url in OVERLAPPING]
    assert len(fixes) == 28

    output = suppress_group_covered_singletons(fixes)

    assert len(output) == 1, "the family card must be the only surviving action"
    survivor = output[0]
    assert survivor["page_url"] == ""
    assert survivor["rule"] == RULE
    assert len(survivor["affected_pages"]) == len(GROUP_PAGES)
    # No page-scope copy of the same rule may remain.
    assert not [f for f in output if f.get("page_url") and f.get("rule") == RULE]


def test_outlier_url_outside_the_group_survives():
    """Requirement: true outliers are preserved, so coverage stays honest."""
    outlier = "https://ike.com/checkout/step-2"
    fixes = [_group_card()] + [_page_row(url) for url in OVERLAPPING] + [_page_row(outlier)]

    output = suppress_group_covered_singletons(fixes)

    survivors = {f.get("page_url") for f in output}
    assert survivors == {"", outlier}


def test_partially_covered_row_survives():
    """A row naming one covered and one uncovered page is not fully duplicated."""
    fixes = [_group_card()]
    straddle = _page_row(GROUP_PAGES[0])
    straddle["affected_pages"] = [GROUP_PAGES[0], "https://ike.com/gift-cards"]
    straddle["page_count"] = 2
    fixes.append(straddle)

    output = suppress_group_covered_singletons(fixes)

    assert len(output) == 2, "a straddling row still names a page the group does not cover"


def test_different_rule_on_a_covered_page_survives():
    """Requirement: a group of one rule never suppresses a different rule."""
    fixes = [_group_card(), _page_row(GROUP_PAGES[0], rule="missing_h1")]

    output = suppress_group_covered_singletons(fixes)

    assert len(output) == 2
    assert {f.get("rule") for f in output} == {RULE, "missing_h1"}


def test_group_coverage_is_keyed_on_the_exact_rule_not_the_family():
    """`broken_page` and `404_error` share a remediation family but are distinct rules.

    Coverage for this path is keyed on the exact rule deliberately: a template
    card lists the pages *its own rule* repairs, and nothing licenses it to
    silence a different rule that merely lands in the same family. Keying on
    fix_dedup_class here would suppress the 404 row and quietly widen the blast
    radius of every group card.
    """
    group = _group_card(pages=GROUP_PAGES[:5])
    group["rule"] = "broken_page"
    group["category"] = "broken_page"
    assert fix_dedup_class(group) == fix_dedup_class(
        {"rule": "404_error", "category": "broken_page"}
    ), "fixture is only meaningful while these two rules share a dedup class"

    output = suppress_group_covered_singletons(
        [group, _page_row(GROUP_PAGES[0], rule="404_error")]
    )

    assert len(output) == 2
    assert {f.get("rule") for f in output} == {"broken_page", "404_error"}


def test_below_threshold_grouping_is_not_authoritative():
    """A two-page raw grouping is not a scanner template card and must not suppress."""
    small = _group_card(pages=GROUP_PAGES[:2])
    fixes = [small, _page_row(GROUP_PAGES[0])]

    output = suppress_group_covered_singletons(fixes)

    assert len(output) == 2


def _pages(urls):
    return [
        {
            "final_url": url,
            "status_code": 200,
            "h1_count": 1,
            "meta_description": "x",
            "canonical": url,
            "page_template_family": "location_landing",
        }
        for url in urls
    ]


def _review(urls):
    """Full review over the Ike shape, through collect_arrays -> prepare_fixes."""
    return run_review({
        "website_url": "https://ike.com",
        "pages": _pages(urls),
        "grouped_findings": [_group_card(pages=urls)],
        "raw_findings": [_page_row(url) for url in urls[:27]],
        "scan_coverage": {
            "pages_found": 167,
            "pages_crawled": len(urls),
            "sampled_pages_sent_to_ai": len(urls),
        },
    })


def test_review_output_carries_one_action_for_the_family():
    """Deduped at source, not hidden by the frontend."""
    review = _review(GROUP_PAGES[:30])

    same_rule = [f for f in review["cleaned_fixes"] if f.get("rule") == RULE]
    assert len(same_rule) == 1, "run_review must emit one action for the family"
    # normalize_fix backfills page_url from the first affected page, so the family
    # card is identified by the page list it repairs, not by a blank page_url.
    assert len(same_rule[0]["affected_pages"]) > 1, "the survivor is the family card"


def test_canonical_snapshot_and_total_fixes_use_the_deduped_rows():
    """canonical_repairs / total_fixes / canonical_action_fix_ids all follow the dedupe."""
    urls = GROUP_PAGES[:30]
    review = _review(urls)
    snapshot = apply_canonical_repair_contract(review, {"crawled_pages": _pages(urls)})

    canonical = snapshot["canonical_repairs"]
    assert snapshot["total_fixes"] == len(canonical)
    assert snapshot["canonical_action_fix_ids"] == [item["fix_id"] for item in canonical]

    same_rule = [item for item in canonical if item.get("rule") == RULE]
    assert len(same_rule) == 1, "the persisted snapshot must not carry duplicate page cards"
    # Every persisted fix_id is distinct, so no duplicate card can reach the UI.
    assert len(set(snapshot["canonical_action_fix_ids"])) == len(canonical)
