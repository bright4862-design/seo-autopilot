from contextlib import asynccontextmanager
import socket

import httpx
import pytest

from app.robots_policy import RobotsPolicy
from app.scanner import build_findings, fetch_and_extract


DISCOVERY_SITEMAP = {
    "discovered_from": ["sitemap"],
    "source_pages": ["/sitemap.xml"],
    "link_text_samples": [],
}
DISCOVERY_INTERNAL = {
    "discovered_from": ["internal_link"],
    "source_pages": ["/source"],
    "link_text_samples": ["Old link"],
}


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get(self, url, *, headers=None, extensions=None):
        pinned = httpx.URL(url)
        authority = (headers or {}).get("Host", "")
        logical_url = f"{pinned.scheme}://{authority}{pinned.raw_path.decode('ascii')}"
        self.calls.append(logical_url)
        response = self.responses[logical_url]
        if isinstance(response, Exception):
            raise response
        return response

    @asynccontextmanager
    async def stream(self, method, url, *, headers=None, extensions=None):
        assert method == "GET"
        yield await self.get(url, headers=headers, extensions=extensions)


@pytest.fixture(autouse=True)
def deterministic_public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))
        ],
    )


@pytest.fixture
def policy():
    return RobotsPolicy("https://example.com/robots.txt", "missing", 404)


def _response(url, status=200, *, location="", body=None, headers=None):
    response_headers = {"content-type": "text/html; charset=utf-8"}
    if location:
        response_headers["location"] = location
    if headers:
        response_headers.update(headers)
    html = body if body is not None else (
        "<html><head><title>Page</title><link rel=\"canonical\" href=\"https://example.com/final\"></head>"
        "<body><h1>Page</h1><p>Useful HTML content.</p></body></html>"
    )
    return httpx.Response(
        status,
        headers=response_headers,
        stream=httpx.ByteStream(html.encode("utf-8")),
        request=httpx.Request("GET", url),
    )


def _rules(page):
    return {finding["rule"] for finding in build_findings([page])}


def _redirect_finding(page):
    return next(
        (finding for finding in build_findings([page]) if str(finding.get("rule", "")).startswith("redirect_")),
        None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 308])
async def test_redirect_to_200_html_is_usable_and_preserves_complete_fetch_evidence(policy, status):
    client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", status, location="/final"),
        "https://example.com/final": _response("https://example.com/final", 200),
    })

    page = await fetch_and_extract(client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_to_usable_page"
    assert "redirect_destination_failed" not in _rules(page)
    assert "internal_link_redirect" in _rules(page)

    evidence = page["redirect_fetch_evidence"]
    assert evidence["requested_url"] == "https://example.com/old"
    assert evidence["redirect_chain"] == [
        {"url": "https://example.com/old", "status": status, "location": "https://example.com/final"}
    ]
    assert evidence["final_url"] == "https://example.com/final"
    assert evidence["final_status"] == 200
    assert evidence["final_content_type"].startswith("text/html")
    assert evidence["body_bytes"] > 0
    assert evidence["html_parse_ok"] is True
    assert evidence["fetch_error"] is None
    assert evidence["canonical_url"] == "https://example.com/final"
    assert evidence["noindex"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("final_status", [404, 500])
async def test_redirect_to_http_error_is_unusable(policy, final_status):
    client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", 301, location="/missing"),
        "https://example.com/missing": _response("https://example.com/missing", final_status),
    })

    page = await fetch_and_extract(client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_destination_unusable"
    assert "redirect_destination_failed" in _rules(page)
    evidence = page["redirect_fetch_evidence"]
    assert evidence["final_status"] == final_status
    assert evidence["final_url"] == "https://example.com/missing"


@pytest.mark.asyncio
async def test_redirect_loop_is_unusable_with_chain_evidence(policy):
    client = FakeClient({
        "https://example.com/a": _response("https://example.com/a", 301, location="/b"),
        "https://example.com/b": _response("https://example.com/b", 302, location="/a"),
    })

    page = await fetch_and_extract(client, "https://example.com/a", DISCOVERY_INTERNAL, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_destination_unusable"
    assert "redirect_loop" in _rules(page)
    assert page["redirect_fetch_evidence"]["fetch_error"] == "redirect_loop"


@pytest.mark.asyncio
async def test_redirect_destination_timeout_is_unverified_not_confirmed_dead_end(policy):
    client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", 301, location="/slow"),
        "https://example.com/slow": httpx.ReadTimeout("timed out"),
    })

    page = await fetch_and_extract(client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)
    findings = build_findings([page])

    assert page["redirect_outcome"] == "redirect_destination_unverified"
    assert "redirect_destination_failed" not in {finding["rule"] for finding in findings}
    finding = next(finding for finding in findings if finding["rule"] == "redirect_destination_unverified")
    assert finding["verification_state"] == "needs_verification"
    assert finding["non_scoring"] is True
    assert finding["redirect_fetch_evidence"]["fetch_error"]


@pytest.mark.asyncio
async def test_noindex_html_destination_is_nonindexable_not_broken(policy):
    noindex_html = (
        '<html><head><title>Hidden</title><meta name="robots" content="noindex">'
        '<link rel="canonical" href="https://example.com/hidden"></head>'
        '<body><h1>Hidden</h1><p>Useful HTML content.</p></body></html>'
    )
    client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", 301, location="/hidden"),
        "https://example.com/hidden": _response("https://example.com/hidden", 200, body=noindex_html),
    })

    page = await fetch_and_extract(client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_to_nonindexable_page"
    assert "redirect_destination_noindex" in _rules(page)
    assert "redirect_destination_failed" not in _rules(page)
    assert page["redirect_fetch_evidence"]["noindex"] is True


@pytest.mark.asyncio
async def test_sitemap_trailing_slash_redirect_is_normalization_not_broken(policy):
    client = FakeClient({
        "https://example.com/about": _response("https://example.com/about", 301, location="/about/"),
        "https://example.com/about/": _response(
            "https://example.com/about/",
            200,
            body=(
                '<html><head><title>About</title><link rel="canonical" href="https://example.com/about/"></head>'
                '<body><h1>About</h1><p>Useful HTML content.</p></body></html>'
            ),
        ),
    })

    page = await fetch_and_extract(client, "https://example.com/about", DISCOVERY_SITEMAP, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_to_usable_page"
    assert _rules(page) == {"sitemap_redirect"}


@pytest.mark.asyncio
async def test_200_html_with_zero_internal_links_is_usable_and_not_a_redirect_failure(policy):
    html = (
        '<html><head><title>Standalone</title><link rel="canonical" href="https://example.com/standalone"></head>'
        '<body><h1>Standalone</h1><p>Useful HTML without links.</p></body></html>'
    )
    client = FakeClient({
        "https://example.com/standalone": _response("https://example.com/standalone", 200, body=html),
    })

    page = await fetch_and_extract(client, "https://example.com/standalone", DISCOVERY_INTERNAL, robots_policy=policy)

    assert page.get("internal_links") in (None, []) or len(page.get("internal_links") or []) == 0
    assert page.get("redirect_outcome") in (None, "")
    assert "redirect_destination_failed" not in _rules(page)
