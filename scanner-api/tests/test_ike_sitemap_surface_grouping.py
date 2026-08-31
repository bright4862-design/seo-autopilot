"""One shared artifact is one repair, however many templates surface it.

Ike's scan 6a9548bd0d7384cc66988ae4 persisted the same sitemap edit as five
separate cards because the redirecting URLs spanned legal, standard, guide,
contact and unclassified pages. The customer fixes one sitemap; the page family
those URLs happen to belong to is evidence, not another task.
"""

from app.scanner import (
    FAILURE_RULES,
    SITE_SURFACE_GUIDANCE,
    GROUP_MIN_AFFECTED,
    SITE_SURFACE_RULES,
    TEMPLATE_RULES,
    group_findings,
    group_template_title,
    grouping_key,
)


def finding(rule: str, url: str, **extra):
    payload = {
        "rule": rule,
        "page_url": url,
        "affected_pages": [url],
        "title": f"{rule} on {url}",
        "priority": "medium",
    }
    payload.update(extra)
    return payload


def ike_sitemap_findings():
    """The exact family spread the Ike FixList fragmented across."""
    return (
        [finding("sitemap_redirect", f"https://ikessandwich.com/legal/terms-{i}") for i in range(3)]
        + [finding("sitemap_redirect", f"https://ikessandwich.com/menu/item-{i}") for i in range(37)]
        + [finding("sitemap_redirect", "https://ikessandwich.com/?utm=unclassified")]
        + [finding("sitemap_redirect", "https://ikessandwich.com/guides/catering")]
        + [finding("sitemap_redirect", "https://ikessandwich.com/contact")]
    )


def titles(cards):
    return [card.get("issue_title") or card.get("title") for card in cards]


def test_one_sitemap_edit_is_one_customer_action():
    findings = ike_sitemap_findings()
    assert len({grouping_key(f) for f in findings}) == 1, "page family must not fragment a site-surface repair"

    cards = group_findings(findings)
    assert len(cards) == 1, f"expected one sitemap repair, got {titles(cards)}"
    assert cards[0]["issue_title"] == "Replace redirecting URLs in the sitemap"


def test_every_affected_url_survives_the_collapse():
    findings = ike_sitemap_findings()
    card = group_findings(findings)[0]
    expected = {f["page_url"] for f in findings}
    assert set(card["affected_pages"]) == expected, "collapsing must not drop evidence"
    assert card["page_count"] == len(expected) == 43


def test_no_singleton_survives_beside_the_group_that_covers_it():
    # The five-way split produced both group cards and raw-titled singletons for
    # the same rule, which is what reached the customer as "the same thing in
    # different words". One key means neither can happen.
    cards = group_findings(ike_sitemap_findings())
    assert len(titles(cards)) == len(set(titles(cards))), "no two cards may carry the same title"
    assert not any(str(title).startswith("sitemap_redirect on ") for title in titles(cards)), (
        "a raw rule title means a finding escaped grouping"
    )


def test_a_lone_sitemap_finding_is_still_reported():
    # Collapsing must not require a crowd: one redirecting sitemap URL is still
    # a real defect, it simply stays a direct finding below the group threshold.
    single = [finding("sitemap_redirect", "https://ikessandwich.com/contact")]
    cards = group_findings(single)
    assert len(cards) == 1
    assert len(cards[0]["affected_pages"]) == 1


def test_different_remediation_surfaces_do_not_collapse():
    findings = (
        ike_sitemap_findings()
        + [finding("internal_link_redirect", f"https://ikessandwich.com/menu/item-{i}") for i in range(5)]
        + [finding("canonical_missing", f"https://ikessandwich.com/locations/{i}") for i in range(6)]
    )
    cards = group_findings(findings)
    shown = titles(cards)
    assert "Replace redirecting URLs in the sitemap" in shown
    assert "Update internal links that pass through redirects" in shown
    assert len(cards) == 3, f"three distinct customer actions expected, got {shown}"
    # Internal links are edited in templates and content; the sitemap is one
    # file. Same redirect symptom, genuinely different work.
    sitemap_key = grouping_key(finding("sitemap_redirect", "https://x.test/a"))
    link_key = grouping_key(finding("internal_link_redirect", "https://x.test/a"))
    assert sitemap_key != link_key


def test_template_repairs_still_separate_by_family():
    # A template repair is per-template work: location pages and legal pages can
    # need genuinely different edits, so these must NOT collapse.
    findings = (
        [finding("canonical_missing", f"https://ikessandwich.com/locations/{i}") for i in range(6)]
        + [finding("canonical_missing", f"https://ikessandwich.com/legal/{i}") for i in range(4)]
    )
    cards = group_findings(findings)
    assert len(cards) == 2, f"template families must stay separate, got {titles(cards)}"
    assert len({grouping_key(f) for f in findings}) == 2


def test_site_surface_set_matches_the_titles_that_ignore_family():
    """The two must not drift.

    group_template_title already encodes which repairs are template work: it
    interpolates the family for those and names a shared artifact for the rest.
    A rule added to one side and not the other would silently re-fragment a
    site-surface repair, or wrongly merge two genuinely different template edits.
    """
    for rule in sorted(TEMPLATE_RULES):
        family_named = group_template_title(rule, "location_landing")
        family_other = group_template_title(rule, "legal_info")
        family_independent = family_named == family_other
        assert family_independent == (rule in SITE_SURFACE_RULES), (
            f"{rule}: title family-independent={family_independent} but "
            f"in SITE_SURFACE_RULES={rule in SITE_SURFACE_RULES}"
        )


def test_two_rules_can_never_merge_however_the_surface_is_labelled():
    """The rule stays in the key, so a mislabelled surface cannot over-collapse.

    This is the safety property that makes the surface set safe to extend: the
    surface removes page family from the key, it never replaces the rule. Two
    genuinely different repairs remain two repairs even if someone files them
    under the same artifact by mistake.
    """
    keys = {grouping_key(finding(rule, "https://x.test/a")) for rule in SITE_SURFACE_RULES}
    assert len(keys) == len(SITE_SURFACE_RULES), "each rule must keep its own key"


def test_surfaces_name_the_artifact_the_customer_actually_edits():
    # The label is documentation of intent, and wrong documentation invites a
    # future change that does group by surface alone. A sitemap entry and an
    # in-page link are edited in different places.
    assert SITE_SURFACE_RULES["sitemap_redirect"] == "xml_sitemap"
    assert SITE_SURFACE_RULES["internal_link_redirect"] == "internal_links"
    assert SITE_SURFACE_RULES["sitemap_redirect"] != SITE_SURFACE_RULES["internal_link_redirect"]
    # Redirect configuration and canonical tags are likewise different surfaces.
    assert SITE_SURFACE_RULES["redirect_chain"] != SITE_SURFACE_RULES["canonical_chain"]
    assert SITE_SURFACE_RULES["redirect_chain"] != SITE_SURFACE_RULES["sitemap_redirect"]


def test_site_surface_rules_are_known_template_rules():
    unknown = set(SITE_SURFACE_RULES) - TEMPLATE_RULES
    assert not unknown, f"site-surface rules must be real template rules: {unknown}"
    assert not (set(SITE_SURFACE_RULES) & FAILURE_RULES), "crawl failures are not a shared repair surface"


def test_failure_rules_still_group_by_family():
    # Untouched by this change: a 404 is fixed per URL, not on one shared
    # artifact, so its grouping is deliberately left alone.
    keys = {
        grouping_key(finding("404_error", "https://ikessandwich.com/legal/a")),
        grouping_key(finding("404_error", "https://ikessandwich.com/menu/a")),
    }
    assert len(keys) == 2
    assert all(key.startswith("failure|404_error|") for key in keys)


def test_group_threshold_is_unchanged():
    # Collapsing by surface must not lower the bar for claiming a template card.
    assert GROUP_MIN_AFFECTED == 3
    two = [finding("sitemap_redirect", f"https://ikessandwich.com/menu/{i}") for i in range(2)]
    cards = group_findings(two)
    assert all(card.get("page_count") in (None, 1) for card in cards), (
        "below the threshold these stay individual findings, not a claimed group"
    )


def test_a_sitemap_card_tells_the_customer_to_edit_the_sitemap():
    """Guidance has to name the artifact, not a page template.

    The template wording -- "fix one representative page/template first" -- is
    not merely vague on a sitemap card, it is wrong: the entry list is generated
    somewhere else, and following that advice would have the customer editing
    pages that are not the defect.
    """
    card = group_findings(ike_sitemap_findings())[0]
    recommendation = card["recommended_value"].lower()
    assert "sitemap" in recommendation
    assert "representative page" not in recommendation
    assert "template" not in recommendation
    assert "canonical" in recommendation, "the fix is the final 200-status canonical URL"


def test_each_site_surface_has_its_own_guidance():
    surfaces = set(SITE_SURFACE_RULES.values())
    assert surfaces == set(SITE_SURFACE_GUIDANCE), (
        "every surface needs artifact-specific guidance, or its cards fall back to template wording"
    )
    for surface, (explanation, recommendation) in SITE_SURFACE_GUIDANCE.items():
        assert explanation.strip() and recommendation.strip(), surface
        assert "representative page/template" not in recommendation, surface


def test_template_repairs_keep_the_template_guidance():
    # The template wording is right where the repair really is a template edit.
    card = group_findings(
        [finding("missing_meta_description", f"https://ikessandwich.com/locations/{i}") for i in range(5)]
    )[0]
    assert "template" in card["recommended_value"].lower()
    # Both halves of the guidance, or a card can explain one repair and
    # recommend another.
    assert "template" in card["plain_english_explanation"].lower()
    assert "sitemap" not in card["plain_english_explanation"].lower()
    assert "sitemap" not in card["recommended_value"].lower()


def test_internal_link_guidance_targets_links_not_pages():
    card = group_findings(
        [finding("internal_link_redirect", f"https://ikessandwich.com/menu/{i}") for i in range(4)]
    )[0]
    assert "link" in card["recommended_value"].lower()
    assert "sitemap" not in card["recommended_value"].lower()
