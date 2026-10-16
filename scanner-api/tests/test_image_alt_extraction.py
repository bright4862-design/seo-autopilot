from app.extract import extract_page
from app.review import compute_health_score_breakdown, run_review
from app.scanner import build_findings


def _extract(images: str) -> dict:
    return extract_page(
        f"<html><head><title>Images</title><meta name='description' content='A useful page'></head>"
        f"<body><h1>Images</h1><p>Useful page content for visitors.</p>{images}</body></html>",
        "https://example.com/images",
        "https://example.com/images",
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )


def test_missing_alt_means_absent_attribute_only():
    absent = _extract('<img src="meaningful.jpg">')
    empty = _extract('<img src="decorative.svg" alt="">')
    whitespace = _extract('<img src="spacer.gif" alt="   ">')
    described = _extract('<img src="product.jpg" alt="Product photo">')

    assert (absent["image_missing_alt_count"], absent["missing_alt_image_count"]) == (1, 1)
    for page in (empty, whitespace, described):
        assert (page["image_missing_alt_count"], page["missing_alt_image_count"]) == (0, 0)


def test_mixed_images_count_only_absent_alt_attributes():
    page = _extract(
        '<img src="one.jpg"><img src="two.svg" alt="">'
        '<img src="three.gif" alt="   "><img src="four.jpg" alt="Four">'
    )
    assert page["image_count"] == 4
    assert page["image_missing_alt_count"] == page["missing_alt_image_count"] == 1


def test_empty_alt_only_page_has_no_repair_or_health_penalty():
    page = _extract('<img src="decorative.svg" alt=""><img src="spacer.gif" alt=" ">')
    findings = build_findings([page])
    assert not [finding for finding in findings if finding.get("rule") == "image_alt_text"]

    reviewed = run_review({
        "website_url": "https://example.com",
        "pages": [page],
        "findings": findings,
        "scan_coverage": {"pages_found": 1, "pages_crawled": 1, "sampled_pages_sent_to_ai": 1},
    })
    assert not [fix for fix in reviewed["recommendations"] if fix.get("rule") == "image_alt_text"]
    breakdown = compute_health_score_breakdown(
        reviewed["recommendations"],
        {"pages_crawled": 1, "pages_found": 1, "sampled_pages_sent_to_ai": 1},
    )
    assert not [key for key in breakdown["action_penalties"] if "image_alt" in key]
