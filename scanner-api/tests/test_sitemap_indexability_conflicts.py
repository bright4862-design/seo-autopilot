from app.scanner import build_findings, group_findings, sitemap_indexability_conflict


def _page(state, *, sources=None, path="/private"):
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "path": path,
        "status_code": 200,
        "fetch_error": "",
        "url_confidence": "sitemap_listed",
        "discovered_from": sources or ["sitemap"],
        "source_pages": ["/sitemap.xml"],
        "link_text_samples": [],
        "indexability_state": state,
        "indexable": state == "Indexable",
        "title": "Page",
        "meta_description": "Description",
        "h1": "Page",
        "h1_count": 1,
        "canonical": f"https://example.com{path}",
        "estimated_page_intent": "standard",
        "image_missing_alt_count": 0,
    }


def test_sitemap_noindex_emits_bounded_conflict():
    findings = build_findings([_page("Noindexed")])
    conflict = next(item for item in findings if item["rule"] == "sitemap_indexability_conflict")

    assert conflict["page_url"] == "/private"
    assert conflict["current_value"] == "Noindexed"
    assert conflict["who_can_do_this"] == "your_web_person"


def test_googlebot_robots_block_in_sitemap_is_a_conflict_not_a_failed_page():
    page = _page("Blocked by robots.txt")
    page.update({
        "status_code": 0,
        "fetch_error": "blocked_by_robots_txt",
        "robots_txt_googlebot_blocked": True,
    })

    findings = build_findings([page])
    rules = {item["rule"] for item in findings}

    assert "sitemap_indexability_conflict" in rules
    assert "failed_page" not in rules


def test_internal_only_noindex_is_not_called_a_sitemap_conflict():
    page = _page("Noindexed", sources=["internal_link"])

    assert sitemap_indexability_conflict(page) is False
    assert not any(
        item["rule"] == "sitemap_indexability_conflict"
        for item in build_findings([page])
    )


def test_unknown_or_access_limited_state_does_not_invent_a_conflict():
    page = _page("Unknown because of access or rendering limitations")

    assert sitemap_indexability_conflict(page) is False
    assert not any(
        item["rule"] == "sitemap_indexability_conflict"
        for item in build_findings([page])
    )


def test_repeated_conflicts_group_without_losing_specific_title():
    pages = [_page("Noindexed", path=f"/products/item-{index}") for index in range(3)]

    grouped = group_findings(build_findings(pages))
    conflict = next(item for item in grouped if item["rule"] == "sitemap_indexability_conflict")

    assert conflict["title"] == "Remove non-indexable URLs from the sitemap"
    assert conflict["page_count"] == 3
    assert conflict["affected_pages"] == [
        "/products/item-0",
        "/products/item-1",
        "/products/item-2",
    ]
