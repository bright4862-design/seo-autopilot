import httpx
import pytest
import socket

from app.robots_policy import (
    RobotsPolicy,
    annotate_robots_evidence,
    load_robots_policy,
)
from app.scanner import run_scan


class _StreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


class _Client:
    def __init__(self, response):
        self.response = response

    async def get(self, _url, **_kwargs):
        return self.response

    def stream(self, _method, _url, **_kwargs):
        return _StreamContext(self.response)


@pytest.fixture(autouse=True)
def deterministic_public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))
        ],
    )


def _response(status, text=""):
    return httpx.Response(
        status,
        text=text,
        request=httpx.Request("GET", "https://example.com/robots.txt"),
    )


@pytest.mark.asyncio
async def test_policy_separates_scanner_and_googlebot_rules(monkeypatch):
    monkeypatch.setattr("app.security.is_public_http_url", lambda _url: True)
    policy = await load_robots_policy(
        _Client(_response(200, "User-agent: Googlebot\nDisallow: /private\n\nUser-agent: *\nAllow: /")),
        "https://example.com",
    )

    assert policy.status == "available"
    assert policy.allowed("Googlebot", "https://example.com/private") is False
    assert policy.allowed("FixListPythonScanner", "https://example.com/private") is True


@pytest.mark.asyncio
async def test_missing_robots_file_is_known_allow_all(monkeypatch):
    monkeypatch.setattr("app.security.is_public_http_url", lambda _url: True)
    policy = await load_robots_policy(_Client(_response(404)), "https://example.com")

    assert policy.status == "missing"
    assert policy.rules_known is True
    assert policy.allowed("Googlebot", "https://example.com/anything") is True


@pytest.mark.asyncio
async def test_access_limited_robots_file_stays_unknown(monkeypatch):
    monkeypatch.setattr("app.security.is_public_http_url", lambda _url: True)
    policy = await load_robots_policy(_Client(_response(403)), "https://example.com")

    assert policy.status == "access_limited"
    assert policy.rules_known is False
    assert policy.allowed("Googlebot", "https://example.com/private") is None


def test_googlebot_block_sets_explicit_indexability_state():
    from urllib import robotparser

    parser = robotparser.RobotFileParser()
    parser.parse(["User-agent: Googlebot", "Disallow: /private", "User-agent: *", "Allow: /"])
    policy = RobotsPolicy("https://example.com/robots.txt", "available", 200, parser)
    page = {"indexable": True, "indexability_state": "Indexable"}

    annotate_robots_evidence(page, policy, "https://example.com/private")

    assert page["robots_txt_googlebot_blocked"] is True
    assert page["robots_txt_scanner_blocked"] is False
    assert page["indexable"] is False
    assert page["indexability_state"] == "Blocked by robots.txt"


def test_unknown_policy_does_not_invent_allow_or_block_evidence():
    policy = RobotsPolicy("https://example.com/robots.txt", "unavailable", 0)
    page = {"indexable": True, "indexability_state": "Indexable"}

    annotate_robots_evidence(page, policy, "https://example.com/page")

    assert page["robots_txt_googlebot_allowed"] is None
    assert page["robots_txt_scanner_allowed"] is None
    assert page["indexability_state"] == "Indexable"


@pytest.mark.asyncio
async def test_scan_does_not_fetch_a_url_disallowed_for_the_scanner(mock_network):
    origin = "https://example.com"
    mock_network({
        f"{origin}/robots.txt": {
            "body": (
                "User-agent: FixListPythonScanner\nDisallow: /private\n\n"
                "User-agent: Googlebot\nDisallow: /private\n"
            ),
            "status": 200,
            "content_type": "text/plain",
        },
        f"{origin}/sitemap.xml": {
            "body": (
                '<?xml version="1.0"?><urlset>'
                f"<url><loc>{origin}/</loc></url>"
                f"<url><loc>{origin}/private</loc></url>"
                "</urlset>"
            ),
            "status": 200,
            "content_type": "application/xml",
        },
        f"{origin}/": {
            "body": "<html><head><title>Home</title></head><body><h1>Home</h1></body></html>",
            "status": 200,
            "content_type": "text/html",
        },
        f"{origin}/private": {
            "body": "<html><head><title>Private</title></head><body><h1>Private</h1></body></html>",
            "status": 200,
            "content_type": "text/html",
        },
    })

    result = await run_scan(origin, scan_mode="basic", concurrency=1)
    private = next(page for page in result["pages"] if page["path"] == "/private")

    assert result["robots_txt_evidence"]["robots_txt_status"] == "available"
    assert private["status_code"] == 0
    assert private["fetch_error"] == "blocked_by_robots_txt"
    assert private["robots_txt_scanner_blocked"] is True
    assert private["robots_txt_googlebot_blocked"] is True
    assert private["indexability_state"] == "Blocked by robots.txt"
    assert not any(
        finding.get("page_url") == "/private" and finding.get("rule") == "failed_page"
        for finding in result["raw_findings"]
    )
