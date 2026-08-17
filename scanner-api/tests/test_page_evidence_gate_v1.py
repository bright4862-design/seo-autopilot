from app.extract import extract_page
from app.page_evidence_gate import PAGE_EVIDENCE_GATE_VERSION, page_evidence_class
from app.review import build_page_pattern_findings, build_scanner_evidence_findings, build_site_fingerprint, prepare_fixes
from app.scanner import build_findings, calculate_health_score

HTML_RULES = {"canonical_missing", "missing_title", "generic_fallback_title", "title_over_pixel_limit", "missing_meta_description", "empty_meta_description", "malformed_meta_description", "missing_h1", "multiple_h1", "schema", "image_alt_text"}

def extracted(html="", *, status=0, error="redirect_validation_failed", content_type=""):
    return extract_page(html, "https://www.funbooker.com/fr", "https://www.funbooker.com/fr", status, content_type, {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []}, fetch_error=error)

def test_funbooker_redirect_validation_failure_only_emits_access_limitation():
    page = extracted()
    assert page["page_evidence_class"] == "failed_access"
    assert page["evidence_gate_version"] == PAGE_EVIDENCE_GATE_VERSION
    findings = build_findings([page])
    assert [finding["rule"] for finding in findings] == ["site_access_limited"]
    assert findings[0]["verification_state"] == "needs_verification"
    assert findings[0]["non_scoring"] is True
    assert not ({finding["rule"] for finding in findings} & HTML_RULES)
    assert calculate_health_score([page], findings) is None

def test_review_pattern_generator_suppresses_html_rules_for_failed_access():
    page = extracted()
    assert build_page_pattern_findings([page]) == []
    body = {"pages_crawled": 1, "pages_found": 1, "verified_failed_pages": [page]}
    fingerprint = build_site_fingerprint(body, [page], "https://www.funbooker.com/fr")
    findings = build_scanner_evidence_findings(body, [page], fingerprint)
    assert [finding["rule"] for finding in findings] == ["site_access_limited"]
    assert findings[0]["score_impact"] == 0

def test_review_drops_legacy_html_findings_when_underlying_page_is_unusable():
    page = extracted()
    body = {"pages_crawled": 1, "pages_found": 1}
    fingerprint = build_site_fingerprint(body, [page], "https://www.funbooker.com/fr")
    playbook = {"label": "general", "money_patterns": [], "priority_pages": [], "priority_issues": [], "demote": [], "owner_rule": ""}
    legacy = [{"rule": "canonical_missing", "category": "canonical", "priority": "high", "title": "Add canonical", "page_url": "/fr", "affected_pages": ["/fr"]}]
    assert prepare_fixes(legacy, fingerprint, body, playbook, [page]) == []

def test_healthy_html_still_generates_normal_findings():
    page = extracted("<html><head><title>Useful page</title></head><body><p>Text</p></body></html>", status=200, error="", content_type="text/html")
    assert page_evidence_class(page) == "usable_html"
    rules = {finding["rule"] for finding in build_findings([page])}
    assert {"missing_meta_description", "missing_h1", "canonical_missing"} <= rules

def test_non_html_and_empty_200_are_not_usable():
    non_html = extracted('{"ok":true}', status=200, error="", content_type="application/json")
    empty = extracted("", status=200, error="", content_type="text/html")
    assert page_evidence_class(non_html) == "non_html"
    assert page_evidence_class(empty) == "incomplete_html"
    assert not ({finding["rule"] for finding in build_findings([non_html, empty])} & HTML_RULES)


def test_access_denied_text_inside_storefront_script_does_not_block_valid_html():
    html = """
    <html>
      <head>
        <title>Jack's Surfboards</title>
        <script type="application/json">
          {"ipBlocker":{"title":{"text":"Access Denied"},"description":{"text":"The site owner may have set restrictions."}}}
        </script>
      </head>
      <body><h1>Jack's Surfboards</h1><p>Shop surfboards and wetsuits.</p></body>
    </html>
    """
    page = extracted(html, status=200, error="", content_type="text/html")
    assert page_evidence_class(page) == "usable_html"


def test_visible_access_denied_challenge_with_http_200_remains_failed_access():
    html = """
    <html>
      <head><title>Access Denied</title></head>
      <body><h1>Access Denied</h1><p>Please contact the site owner for access.</p></body>
    </html>
    """
    page = extracted(html, status=200, error="", content_type="text/html")
    assert page_evidence_class(page) == "failed_access"
