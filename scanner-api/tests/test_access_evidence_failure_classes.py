"""Access-classification contract for the four monitored failure classes.

These are generic classes, not domains. The same code must handle any site that
challenges, rate-limits, or returns crawler-invented URLs:

* Viator / RATP -- a WAF or security challenge must never be audited for SEO.
* Meilleurtaux  -- HTTP 429 is an access limitation, never a customer defect.
* Meilleurtaux  -- a URL the crawler invented carries no repair authority.

The assertions are behavioral: what class a page lands in, and which findings
may be produced from it. None of them match on copy.
"""

import pytest

from app.artifact_filter import record_artifact
from app.extract import extract_page
from app.page_evidence_gate import classify_page_evidence, page_evidence_class
from app.scanner import build_findings

# A realistic 200-status interstitial: the body is a challenge, not the site.
CHALLENGE_HTML = """<!doctype html><html><head>
<title>Just a moment...</title><meta name="description" content="Checking"></head>
<body><div class="cf-chl-wrapper">Checking your browser before accessing.</div>
<h1>Verify you are human</h1></body></html>"""

ACCESS_DENIED_HTML = """<!doctype html><html><head><title>Blocked</title></head>
<body><h1>Access Denied</h1><p>You do not have permission.</p></body></html>"""

REAL_HTML = """<!doctype html><html><head><title>Paris day tours</title>
<meta name="description" content="Book guided tours in Paris."></head>
<body><h1>Paris day tours</h1><a href="/tours/eiffel">Eiffel</a></body></html>"""


def _empty_discovery() -> dict:
    return {"discovered_from": "seed", "source_pages": [], "link_text_samples": []}


# ------------------------------------------------ WAF / security challenge --

@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_error_status_is_never_usable_evidence(status):
    assert classify_page_evidence(status_code=status, content_type="text/html", html=REAL_HTML) == "failed_access"


@pytest.mark.parametrize("body", [CHALLENGE_HTML, ACCESS_DENIED_HTML])
def test_apparent_200_challenge_body_is_not_usable_evidence(body):
    """The Viator/RATP class: HTTP 200 does not make a challenge page auditable."""
    assert classify_page_evidence(status_code=200, content_type="text/html", html=body) == "failed_access"


@pytest.mark.parametrize("body", [CHALLENGE_HTML, ACCESS_DENIED_HTML])
def test_challenge_cannot_regain_authority_when_the_stamp_is_lost(body):
    """A challenge must stay non-authoritative even if re-derived downstream."""
    page = {"status_code": 200, "content_type": "text/html", "html_size": len(body), "_html": body}
    assert page_evidence_class(page) == "failed_access"


def test_a_genuine_page_is_still_usable_evidence():
    """The gate must fail closed on challenges without suppressing real pages."""
    assert classify_page_evidence(status_code=200, content_type="text/html", html=REAL_HTML) == "usable_html"


@pytest.mark.parametrize("body", [CHALLENGE_HTML, ACCESS_DENIED_HTML])
def test_no_seo_findings_are_generated_from_challenge_html(body):
    """A challenge page must never yield title/meta/canonical/H1 repairs."""
    page = extract_page(body, "https://example.com/", "https://example.com/", 200, "text/html", _empty_discovery())
    assert page["page_evidence_class"] == "failed_access"

    findings = build_findings([page])
    seo_rules = {
        "missing_meta_description", "empty_meta_description", "malformed_meta_description",
        "meta_description_unusable", "missing_title", "duplicate_title", "missing_h1",
        "canonical_missing", "missing_canonical", "thin_content",
    }
    produced = {str(f.get("rule") or "") for f in findings}
    assert not (produced & seo_rules), f"challenge page produced SEO repairs: {produced & seo_rules}"


def test_challenge_title_never_becomes_a_customer_facing_title_finding():
    """"Just a moment..." must not be audited as the site's real page title."""
    page = extract_page(
        CHALLENGE_HTML, "https://example.com/", "https://example.com/", 200, "text/html", _empty_discovery()
    )
    for finding in build_findings([page]):
        assert "just a moment" not in str(finding.get("current_value") or "").lower()


# ------------------------------------------------------ rate limiting (429) --

def test_429_is_classified_as_rate_limited_not_broken():
    """The Meilleurtaux class: 429 is an access limitation, not a dead page."""
    page = extract_page("", "https://example.com/a", "https://example.com/a", 429, "text/html", _empty_discovery())
    findings = build_findings([page])
    rules = {str(f.get("rule") or "") for f in findings}

    assert "404_error" not in rules, "429 must never be reported as a broken page"
    assert "410_error" not in rules
    assert "broken_page" not in rules
    if rules:
        assert "rate_limited_page" in rules or "site_access_limited" in rules, rules


def test_429_evidence_is_marked_as_needing_verification():
    """A rate-limited page is not confirmed evidence about the customer's site."""
    page = extract_page("", "https://example.com/a", "https://example.com/a", 429, "text/html", _empty_discovery())
    for finding in build_findings([page]):
        if str(finding.get("rule")) == "rate_limited_page":
            assert finding.get("evidence_status") == "needs_verification"


def test_429_page_is_not_usable_seo_evidence():
    assert classify_page_evidence(status_code=429, content_type="text/html", html="") == "failed_access"


# -------------------------------------------------------- URL provenance ----

def test_crawler_invented_url_has_zero_repair_authority():
    """A URL that exists only because of crawler normalization is not a defect.

    FixList may not claim a broken internal link unless the audited site
    actually emitted it.
    """
    artifacts: list[dict] = []
    record_artifact(artifacts, "https://example.com/%2Fwp-json%2Foembed", "normalization", "https://example.com/", "")
    assert artifacts, "artifact recording produced no page"

    invented = artifacts[0]
    invented.update({"status_code": 404, "path": "/%2Fwp-json%2Foembed"})
    assert invented["url_confidence"] == "crawler_artifact"

    assert build_findings([invented]) == [], "a crawler-invented URL became a customer finding"


def test_a_real_site_emitted_broken_link_keeps_its_source_provenance():
    """Genuine broken links stay reportable, and carry where they came from."""
    page = extract_page("", "https://example.com/gone", "https://example.com/gone", 404, "text/html", {
        "discovered_from": "link",
        "source_pages": ["https://example.com/"],
        "link_text_samples": ["Old page"],
    })
    findings = build_findings([page])
    assert findings, "a genuinely linked 404 must still be reportable"
    for finding in findings:
        assert finding.get("source_pages"), "a broken-link finding must carry source-page provenance"
