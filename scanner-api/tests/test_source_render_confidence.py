import pytest

from app.content_evidence_findings import content_evidence_findings
from app.extract import extract_page
from app.missing_h1_contract import build_missing_h1_comparison_evidence
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.scan_job import build_local_review
from app.scan_limits import scan_page_limit

ORIGIN = "https://example.org"


def visit(path, body, head=""):
    url = ORIGIN + path
    document = f"<html><head><title>A guide</title>{head}</head><body>{body}</body></html>"
    return extract_page(document, url, url, 200, "text/html", {})


@pytest.mark.parametrize("cap", [150, 500])
def test_javascript_shells_keep_their_source_evidence_without_scoring(cap):
    chrome = "<nav>" + "Available activities " * 90 + "</nav>"
    shell = visit("/results?market=a", chrome + "<main></main><script src='/search.js'></script>")
    static = visit("/results?market=b", "<main><p>Public activities listed here.</p></main>")
    result = {"website_url": ORIGIN, "pages": [shell, static], "pages_crawled": 2,
              "pages_found": 2, "scan_mode": f"standard_{cap}",
              "raw_findings": [{"rule": "missing_h1", "category": "thin_content",
                                "affected_pages": [shell["url"], static["url"]]}]}
    with scan_page_limit(cap):
        review = build_local_review(result)
        evidence = build_missing_h1_comparison_evidence([shell, static], scan_origin=ORIGIN,
            identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    cards = review["canonical_repairs"]
    heading = next(x for x in cards if x["rule"] == "missing_h1")
    assert heading["affected_pages"] == [static["url"]]
    for rule in ("rendered_heading_review", "rendered_template_review"):
        item = next(x for x in cards if x["rule"] == rule)
        assert item["affected_pages"] == [shell["url"]]
        assert item["non_scoring"] and item["score_impact"] == 0
        assert item["action_priority"] == "review"
        assert item["verification_state"] == "needs_verification"
        assert item["repair_observation_samples"]
        assert rule not in {f["rule"] for f in review["top_recommended_actions"]}
    by_url = {x["page_url"]: x for x in evidence["observations"]}
    assert by_url[shell["url"]]["finding_present"] is None
    assert by_url[static["url"]]["finding_present"] is True
    assert shell["visible_template_evidence"]["state"] == "fail"
    assert any(x["rule"] == "missing_meta_description" for x in cards)


@pytest.mark.parametrize("body,head,expected", [
    ("<main><h1>#location#</h1></main><script src='/location.js'></script>", "", "rendered_template_review"),
    ("<main><h1>#location#</h1></main><script type='application/ld+json'>{}</script>", "", "visible_template_content"),
    ("<main></main>", "", "visible_template_content"),
    ("<main>Lorem ipsum dolor sit amet</main><script src='/analytics.js'></script>", "", "visible_template_content"),
    ("<main></main><iframe src='/portal'></iframe>", "", "rendered_template_review"),
    ("<main></main><script src='/form.js'></script>", "<meta name='robots' content='noindex, follow'>", "rendered_template_review"),
    ("<main>Public article</main><script src='/app.js'></script>", "<meta name='description' content='#location#'>", "visible_template_content"),
])
def test_distinguishes_static_placeholders_embeds_and_source_directives(body, head, expected):
    p = visit("/location", body, head)
    r = [x for x in content_evidence_findings([p]) if x["rule"] in {"visible_template_content", "rendered_template_review"}]
    assert [x["rule"] for x in r] == [expected]
    if "noindex" in head:
        assert "noindex" in p["robots"]
    assert bool(r[0].get("non_scoring")) == (expected == "rendered_template_review")


def test_image_named_heading_and_decorative_image_heading():
    named = visit("/rewards", "<h1><img src='/hero' alt='Welcome to the rewards program'></h1>")
    decorative = visit("/empty", "<h1><img src='/hero' alt=''></h1>")
    assert (named["h1_count"], named["h1"]) == (1, "Welcome to the rewards program")
    assert decorative["h1_count"] == 0


@pytest.mark.parametrize("change,should_lower", [
    ({}, True), ({"noindex": True}, False), ({"final_status": 429}, False),
    ({"final_url": "https://example.net/fr/"}, False),
    ({"html_parse_ok": False}, False), ({"last_location": "/signin"}, False),
    ({"status": 404}, False), ({"market": "de"}, False),
])
def test_only_proven_alias_to_sampled_locale_lowers_redirect_urgency(change, should_lower):
    from app.review_calibration import apply_review_evidence_calibration

    urls = [ORIGIN + "/", "https://www.example.org/", "https://www.example.org/fr/"]
    hops = [{"url": urls[0], "status": change.get("status", 301), "location": urls[1]},
            {"url": urls[1], "status": 302, "location": change.get("last_location", urls[2])}]
    details = {"requested_url": urls[0], "final_url": urls[2], "final_status": 200, "html_parse_ok": True,
               "noindex": False, "classification": "redirect_to_usable_page", "redirect_chain": hops, **change}
    fix = {"rule": "redirect_chain", "page_count": 1, "affected_pages": urls[:1], "priority": "critical",
           "redirect_chain": urls, "redirect_hop_count": 2, "redirect_destination_indexability_state": "Indexable",
           "redirect_fetch_evidence": details}
    result = apply_review_evidence_calibration({"recommendations": [fix]}, {
        "sampling_evidence": {"markets_sampled": {change.get("market", "fr"): 12}}})
    calibrated = result["recommendations"][0]
    assert (calibrated["priority"] == "low") == should_lower
    assert bool(calibrated.get("non_scoring")) == should_lower
    if should_lower:
        assert calibrated["evidence_status"] == "confirmed" and not result["top_recommended_actions"]
