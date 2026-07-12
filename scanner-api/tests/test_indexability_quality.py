from app.extract import extract_page
from app.indexability_quality import annotate_indexability_quality, summarize_indexability_quality
from app.scanner import build_findings, group_findings


SITEMAP_DISCOVERY = {
    "discovered_from": ["sitemap"],
    "source_pages": ["/sitemap.xml"],
    "link_text_samples": [],
}
INTERNAL_DISCOVERY = {
    "discovered_from": ["internal_link"],
    "source_pages": ["/navigation"],
    "link_text_samples": ["Old page"],
}


def _page(
    url="https://example.com/page",
    *,
    title="Page",
    h1="Page",
    body="Useful page content for visitors.",
    head="",
    discovery=None,
):
    return extract_page(
        f"<html><head><title>{title}</title>{head}</head><body><h1>{h1}</h1><p>{body}</p></body></html>",
        url,
        url,
        200,
        "text/html",
        discovery or INTERNAL_DISCOVERY,
    )


def test_high_confidence_200_error_page_becomes_soft_404():
    page = _page(
        "https://example.com/missing-product",
        title="404 Page Not Found",
        h1="Page not found",
        body="Sorry, the product you requested does not exist.",
        discovery=SITEMAP_DISCOVERY,
    )

    annotate_indexability_quality(page)
    findings = build_findings([page])
    soft_404 = next(item for item in findings if item["rule"] == "soft_404")

    assert page["soft_404_suspected"] is True
    assert page["indexable"] is False
    assert page["indexability_state"] == "Soft 404"
    assert soft_404["priority"] == "high"
    assert soft_404["confidence_score"] == 92
    assert not any(item["rule"] in {"missing_meta_description", "missing_h1"} for item in findings)


def test_long_article_about_404_errors_is_not_mislabeled():
    body = " ".join(["diagnostic guidance"] * 180)
    page = _page(
        "https://example.com/blog/understanding-404-errors",
        title="Understanding 404 Not Found Errors",
        h1="How to diagnose 404 errors",
        body=body,
    )

    annotate_indexability_quality(page)

    assert page["word_count"] > 250
    assert page["soft_404_suspected"] is False
    assert page["indexability_state"] == "Indexable"


def test_generic_index_and_googlebot_noindex_create_conflict():
    page = _page(
        head=(
            '<meta name="robots" content="index, follow">'
            '<meta name="googlebot" content="noindex, follow">'
        ),
        discovery=SITEMAP_DISCOVERY,
    )

    annotate_indexability_quality(page)
    finding = next(item for item in build_findings([page]) if item["rule"] == "robots_directive_conflict")

    assert "robots_directive_conflict" in page["indexability_conflicts"]
    assert finding["priority"] == "high"
    assert finding["confidence_score"] == 96


def test_meta_noindex_and_x_robots_index_are_detected_as_conflicting():
    page = extract_page(
        '<html><head><title>Page</title><meta name="robots" content="noindex"></head><body><h1>Page</h1></body></html>',
        "https://example.com/page",
        "https://example.com/page",
        200,
        "text/html",
        INTERNAL_DISCOVERY,
        response_headers={"x-robots-tag": ["index, follow"]},
    )

    annotate_indexability_quality(page)

    assert "robots_directive_conflict" in page["indexability_conflicts"]
    assert any("X-Robots-Tag" in signal for signal in page["indexability_conflict_signals"])


def test_noindex_with_different_canonical_creates_separate_conflict():
    page = _page(
        head=(
            '<meta name="robots" content="noindex">'
            '<link rel="canonical" href="https://example.com/preferred">'
        ),
    )

    annotate_indexability_quality(page)
    finding = next(item for item in build_findings([page]) if item["rule"] == "noindex_canonical_conflict")

    assert "noindex_with_canonical" in page["indexability_conflicts"]
    assert page["indexability_state"] == "Noindexed"
    assert finding["canonical_target_url"] if "canonical_target_url" in finding else True


def test_validated_canonical_target_classifies_source_as_canonicalized():
    page = _page(
        head='<link rel="canonical" href="https://example.com/preferred">',
        discovery=SITEMAP_DISCOVERY,
    )
    page.update({
        "canonical_target_state": "valid",
        "canonical_target_url": "https://example.com/preferred",
    })

    annotate_indexability_quality(page)
    finding = next(item for item in build_findings([page]) if item["rule"] == "sitemap_canonicalized_url")

    assert page["canonicalized_by_valid_target"] is True
    assert page["indexable"] is False
    assert page["indexability_state"] == "Canonicalized"
    assert finding["canonical_target_url"] == "https://example.com/preferred"


def test_broken_canonical_target_does_not_falsely_make_source_nonindexable():
    page = _page(head='<link rel="canonical" href="https://example.com/missing">')
    page.update({
        "canonical_target_state": "target_failed",
        "canonical_target_url": "https://example.com/missing",
        "canonical_target_status_code": 404,
    })

    annotate_indexability_quality(page)

    assert page["canonicalized_by_valid_target"] is False
    assert page["indexable"] is True
    assert page["indexability_state"] == "Indexable"


def test_repeated_quality_findings_group_by_template():
    pages = []
    for index in range(3):
        page = _page(
            f"https://example.com/products/missing-{index}",
            title="404 Page Not Found",
            h1="Page not found",
            body="This product is unavailable.",
        )
        annotate_indexability_quality(page)
        pages.append(page)

    grouped = group_findings(build_findings(pages))
    finding = next(item for item in grouped if item["rule"] == "soft_404")

    assert finding["page_count"] == 3
    assert finding["title"] == "Return real 404 or 410 responses for missing pages"


def test_summary_reports_states_conflicts_and_soft_404s():
    soft = _page(title="404 Not Found", h1="Page not found", body="Missing.")
    conflict = _page(
        head=(
            '<meta name="robots" content="index">'
            '<meta name="googlebot" content="noindex">'
        )
    )
    for page in (soft, conflict):
        annotate_indexability_quality(page)

    summary = summarize_indexability_quality([soft, conflict])

    assert summary["soft_404_count"] == 1
    assert summary["conflict_counts"]["robots_directive_conflict"] == 1
    assert summary["state_counts"]["Soft 404"] == 1
