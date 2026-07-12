import httpx
import pytest

from app.redirect_validation import fetch_with_redirect_evidence, summarize_redirect_evidence
from app.robots_policy import RobotsPolicy
from app.scanner import build_findings, fetch_and_extract

DISCOVERY_SITEMAP = {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"], "link_text_samples": []}
DISCOVERY_INTERNAL = {"discovered_from": ["internal_link"], "source_pages": ["/source"], "link_text_samples": ["Old link"]}


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


class SelectivePolicy:
    url = "https://example.com/robots.txt"

    def __init__(self, scanner_blocked=None, googlebot_blocked=None):
        self.scanner_blocked = set(scanner_blocked or [])
        self.googlebot_blocked = set(googlebot_blocked or [])

    def allowed(self, user_agent, url):
        if user_agent == "FixListPythonScanner":
            return url not in self.scanner_blocked
        if user_agent == "Googlebot":
            return url not in self.googlebot_blocked
        return True


def _response(url, status=200, *, location="", body=None, headers=None):
    response_headers = {"content-type": "text/html"}
    if location:
        response_headers["location"] = location
    if headers:
        response_headers.update(headers)
    html = body if body is not None else "<html><head><title>Page</title></head><body><h1>Page</h1></body></html>"
    return httpx.Response(status, text=html, headers=response_headers, request=httpx.Request("GET", url))


@pytest.mark.asyncio
async def test_single_redirect_preserves_source_and_destination_indexability(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", 301, location="/new"),
        "https://example.com/new": _response("https://example.com/new", 200),
    })
    page = await fetch_and_extract(client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=RobotsPolicy("https://example.com/robots.txt", "missing", 404))
    assert page["redirect_state"] == "single_redirect"
    assert page["redirect_hop_count"] == 1
    assert page["redirect_source_path"] == "/old"
    assert page["redirect_destination_url"] == "https://example.com/new"
    assert page["redirect_destination_indexability_state"] == "Indexable"
    assert page["indexability_state"] == "Redirected"
    assert page["indexable"] is False


@pytest.mark.asyncio
async def test_trailing_slash_redirect_is_not_mislabeled_as_a_loop(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    client = FakeClient({
        "https://example.com/fr": _response("https://example.com/fr", 301, location="/fr/"),
        "https://example.com/fr/": _response("https://example.com/fr/", 200),
    })
    policy = RobotsPolicy("https://example.com/robots.txt", "missing", 404)

    page = await fetch_and_extract(client, "https://example.com/fr", DISCOVERY_SITEMAP, robots_policy=policy)

    assert client.calls == ["https://example.com/fr", "https://example.com/fr/"]
    assert page["redirect_state"] == "single_redirect"
    assert page["redirect_chain"] == ["https://example.com/fr", "https://example.com/fr/"]
    assert page["redirect_destination_url"] == "https://example.com/fr/"


@pytest.mark.asyncio
async def test_redirect_chain_and_loop_are_explicit(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    policy = RobotsPolicy("https://example.com/robots.txt", "missing", 404)
    chain_client = FakeClient({
        "https://example.com/a": _response("https://example.com/a", 301, location="/b"),
        "https://example.com/b": _response("https://example.com/b", 302, location="/c"),
        "https://example.com/c": _response("https://example.com/c", 200),
    })
    loop_client = FakeClient({
        "https://example.com/a": _response("https://example.com/a", 301, location="/b"),
        "https://example.com/b": _response("https://example.com/b", 302, location="/a"),
    })
    chain_page = await fetch_and_extract(chain_client, "https://example.com/a", DISCOVERY_INTERNAL, robots_policy=policy)
    loop_page = await fetch_and_extract(loop_client, "https://example.com/a", DISCOVERY_INTERNAL, robots_policy=policy)
    assert chain_page["redirect_state"] == "redirect_chain"
    assert chain_page["redirect_hop_count"] == 2
    assert loop_page["redirect_state"] == "redirect_loop"
    assert loop_page["redirect_chain"][-1] == "https://example.com/a"


@pytest.mark.asyncio
async def test_redirect_destination_noindex_and_failure_generate_specific_findings(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    policy = RobotsPolicy("https://example.com/robots.txt", "missing", 404)
    noindex_client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", 301, location="/hidden"),
        "https://example.com/hidden": _response("https://example.com/hidden", 200, body='<html><head><title>Hidden</title><meta name="robots" content="noindex"></head><body><h1>Hidden</h1></body></html>'),
    })
    failed_client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", 301, location="/missing"),
        "https://example.com/missing": _response("https://example.com/missing", 404),
    })
    noindex_page = await fetch_and_extract(noindex_client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)
    failed_page = await fetch_and_extract(failed_client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)
    assert "redirect_destination_noindex" in {item["rule"] for item in build_findings([noindex_page])}
    assert "redirect_destination_failed" in {item["rule"] for item in build_findings([failed_page])}


@pytest.mark.asyncio
async def test_robots_blocked_redirect_destination_is_not_fetched(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    client = FakeClient({"https://example.com/old": _response("https://example.com/old", 301, location="/private")})
    policy = SelectivePolicy(scanner_blocked={"https://example.com/private"}, googlebot_blocked={"https://example.com/private"})
    page = await fetch_and_extract(client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)
    finding = next(item for item in build_findings([page]) if item["rule"] == "redirect_destination_blocked")
    assert client.calls == ["https://example.com/old"]
    assert page["redirect_destination_indexability_state"] == "Blocked by robots.txt"
    assert finding["priority"] == "medium"


@pytest.mark.asyncio
async def test_sitemap_and_internal_link_redirects_have_bounded_source_findings(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    responses = {
        "https://example.com/old": _response("https://example.com/old", 301, location="/new"),
        "https://example.com/new": _response("https://example.com/new", 200),
    }
    policy = RobotsPolicy("https://example.com/robots.txt", "missing", 404)
    sitemap_page = await fetch_and_extract(FakeClient(responses), "https://example.com/old", DISCOVERY_SITEMAP, robots_policy=policy)
    internal_page = await fetch_and_extract(FakeClient(responses), "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)
    assert [item["rule"] for item in build_findings([sitemap_page])] == ["sitemap_redirect"]
    assert [item["rule"] for item in build_findings([internal_page])] == ["internal_link_redirect"]


@pytest.mark.asyncio
async def test_summary_counts_redirect_sources(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    policy = RobotsPolicy("https://example.com/robots.txt", "missing", 404)
    responses = {
        "https://example.com/old": _response("https://example.com/old", 301, location="/new"),
        "https://example.com/new": _response("https://example.com/new", 200),
    }
    sitemap_page = await fetch_and_extract(FakeClient(responses), "https://example.com/old", DISCOVERY_SITEMAP, robots_policy=policy)
    internal_page = await fetch_and_extract(FakeClient(responses), "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)
    summary = summarize_redirect_evidence([sitemap_page, internal_page])
    assert summary["redirected_pages"] == 2
    assert summary["sitemap_redirects"] == 1
    assert summary["internal_link_redirects"] == 1


@pytest.mark.asyncio
async def test_trace_function_marks_chain_limit(monkeypatch):
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)
    client = FakeClient({
        "https://example.com/a": _response("https://example.com/a", 301, location="/b"),
        "https://example.com/b": _response("https://example.com/b", 302, location="/c"),
    })
    response, evidence = await fetch_with_redirect_evidence(client, "https://example.com/a", RobotsPolicy("https://example.com/robots.txt", "missing", 404), max_redirects=1)
    assert response is None
    assert evidence["state"] == "redirect_chain_limit_exceeded"
    assert evidence["truncated"] is True
