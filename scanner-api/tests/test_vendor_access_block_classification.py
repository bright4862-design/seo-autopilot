import pytest

from app.evidence_quality import evaluate_evidence_quality
from app.extract import extract_page
from app.page_evidence_gate import (
    PAGE_EVIDENCE_GATE_VERSION,
    classify_page_evidence,
    detect_access_block,
    page_evidence_class,
)
from app.review import is_blocked_access_page
from app.scan_job import terminal_crawl_limitation
from app.scanner import transient_pressure_kind


DISCOVERY = {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []}
SITEGROUND_HTML = (
    '<html><head><link rel="icon" href="data:;">'
    '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/?r=%2F&y=ipr:34.76.10.20:1789720000.123">'
    "</meta></head></html>"
)
REAL_HTML = (
    "<!doctype html><html><head><title>Useful page</title></head>"
    "<body><h1>Useful page</h1><p>This is ordinary customer content.</p></body></html>"
)


def test_siteground_202_challenge_is_stamped_blocked_and_terminal_access_limited():
    page = extract_page(
        SITEGROUND_HTML,
        "https://example.com/",
        "https://example.com/",
        202,
        "text/html",
        DISCOVERY,
        response_headers={
            "sg-captcha": "challenge",
            "x-robots-tag": "noindex",
            "server": "nginx",
            "x-secret-debug": "must-not-persist",
        },
    )

    assert page["evidence_gate_version"] == PAGE_EVIDENCE_GATE_VERSION
    assert page["page_evidence_class"] == "failed_access"
    assert page["access_block_vendor"] == "siteground"
    assert page["access_block_kind"] == "challenge"
    assert page["access_block_signal"] == "sg-captcha"
    assert page["access_block_headers"] == {
        "server": "nginx",
        "sg-captcha": "challenge",
    }
    assert is_blocked_access_page(page) is True

    limitation = terminal_crawl_limitation({"pages": [page]})
    assert limitation is not None
    assert limitation["code"] == "scan_access_limited"
    assert "SiteGround" in limitation["detail"]
    assert "challenge" in limitation["detail"].lower()
    assert "try again later" not in limitation["detail"].lower()

    quality = evaluate_evidence_quality({
        "pages_found": 1,
        "pages_crawled": 1,
        "queued_remaining": 0,
        "crawled_pages": [page],
        "crawl_timing": {
            "queue_exhausted": True,
            "failed_fetch_count": 1,
        },
    })
    assert quality["coverage_state"] == "access_limited"
    assert "access_limited" in quality["coverage_reasons"]


def test_siteground_meta_refresh_is_a_challenge_without_header():
    detected = detect_access_block(202, {}, SITEGROUND_HTML)
    assert detected == {
        "vendor": "siteground",
        "kind": "challenge",
        "signal": "sgcaptcha_meta_refresh",
    }
    assert classify_page_evidence(
        status_code=202,
        content_type="text/html",
        html=SITEGROUND_HTML,
    ) == "failed_access"


def test_cloudflare_header_alone_marks_challenge_without_body_marker():
    detected = detect_access_block(
        403,
        {
            "cf-mitigated": "challenge",
            "cf-ray": "abc123-CDG",
            "server": "cloudflare",
        },
        "<html><body>Request denied</body></html>",
    )
    assert detected == {
        "vendor": "cloudflare",
        "kind": "challenge",
        "signal": "cf-mitigated",
    }
    assert classify_page_evidence(
        status_code=403,
        content_type="text/html",
        html="<html><body>Request denied</body></html>",
        response_headers={"cf-mitigated": "challenge"},
    ) == "failed_access"


@pytest.mark.parametrize(
    ("headers", "body", "vendor"),
    [
        ({"x-datadome": "protected"}, "<html><body>captcha-delivery.com</body></html>", "datadome"),
        ({"x-iinfo": "abc"}, "<html><body>/_Incapsula_Resource</body></html>", "imperva"),
        ({"x-sucuri-id": "123"}, "<html><body>Sucuri WebSite Firewall</body></html>", "sucuri"),
        ({"server": "AkamaiGHost"}, "<html><body><h1>Access Denied</h1></body></html>", "akamai"),
        ({}, "<html><body>Your access to this site has been limited</body></html>", "wordfence"),
    ],
)
def test_vendor_block_pages_are_attributed(headers, body, vendor):
    detected = detect_access_block(403, headers, body)
    assert detected is not None
    assert detected["vendor"] == vendor
    assert detected["kind"] == "block"


@pytest.mark.parametrize(
    "headers",
    [
        {"x-datadome": "edge-present"},
        {"x-iinfo": "edge-present"},
        {"x-sucuri-id": "edge-present"},
        {"server": "AkamaiGHost"},
    ],
)
def test_vendor_headers_do_not_turn_normal_200_html_into_a_block(headers):
    assert detect_access_block(200, headers, REAL_HTML) is None
    assert classify_page_evidence(
        status_code=200,
        content_type="text/html",
        html=REAL_HTML,
        response_headers=headers,
    ) == "usable_html"


def test_article_text_that_mentions_siteground_path_is_not_a_challenge():
    article = (
        "<html><head><title>Security guide</title></head><body><h1>Security guide</h1>"
        "<p>An article can mention /.well-known/sgcaptcha/ without being a challenge.</p></body></html>"
    )
    assert detect_access_block(200, {}, article) is None
    assert classify_page_evidence(
        status_code=200,
        content_type="text/html",
        html=article,
    ) == "usable_html"


def test_plain_202_without_challenge_stays_incomplete_html():
    assert detect_access_block(202, {}, REAL_HTML) is None
    assert classify_page_evidence(
        status_code=202,
        content_type="text/html",
        html=REAL_HTML,
    ) == "incomplete_html"


def test_503_vendor_challenge_is_not_retried_as_transient_pressure():
    page = extract_page(
        "<html><body>Sucuri WebSite Firewall</body></html>",
        "https://example.com/",
        "https://example.com/",
        503,
        "text/html",
        DISCOVERY,
        response_headers={"x-sucuri-id": "abc"},
    )
    assert page["access_block_kind"] == "block"
    assert transient_pressure_kind(page) == ""


def test_429_remains_rate_limit_and_retryable():
    page = extract_page(
        "",
        "https://example.com/",
        "https://example.com/",
        429,
        "text/html",
        DISCOVERY,
        response_headers={"server": "cloudflare"},
    )
    assert page["access_block_kind"] == "rate_limit"
    assert page["access_block_vendor"] == "cloudflare"
    assert transient_pressure_kind(page) == "429"


def test_fallback_treats_stamped_challenge_as_failed_access():
    page = {
        "status_code": 202,
        "content_type": "text/html",
        "html_size": 100,
        "access_block_kind": "challenge",
        "access_block_vendor": "siteground",
    }
    assert page_evidence_class(page) == "failed_access"
