import time
import socket

import httpx
import pytest

from app.canonical_validation import validate_canonical_targets
from app.extract import extract_page
from app.robots_policy import RobotsPolicy
from app.scanner import build_findings


DISCOVERY = {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"], "link_text_samples": []}


def _page(url: str, *, canonical: str = "", robots: str = "", status: int = 200):
    canonical_tag = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    robots_tag = f'<meta name="robots" content="{robots}">' if robots else ""
    return extract_page(
        f"<html><head><title>Page</title>{canonical_tag}{robots_tag}</head><body><h1>Page</h1></body></html>",
        url,
        url,
        status,
        "text/html",
        DISCOVERY,
    )


class _StreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def _response_for(self, url, headers=None):
        pinned = httpx.URL(url)
        logical_url = f"{pinned.scheme}://{(headers or {}).get('Host', '')}{pinned.raw_path.decode('ascii')}"
        self.calls.append(logical_url)
        response = self.responses[logical_url]
        if isinstance(response, Exception):
            raise response
        return response

    async def get(self, url, *, headers=None, extensions=None):
        return self._response_for(url, headers=headers)

    def stream(self, _method, url, *, headers=None, extensions=None):
        return _StreamContext(self._response_for(url, headers=headers))


@pytest.fixture(autouse=True)
def deterministic_public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))
        ],
    )


def _response(url: str, status: int, *, body="<html><head><title>Target</title></head><body><h1>Target</h1></body></html>", headers=None):
    return httpx.Response(
        status,
        headers=headers or {"content-type": "text/html"},
        stream=httpx.ByteStream(body.encode("utf-8")),
        request=httpx.Request("GET", url),
    )


@pytest.mark.asyncio
async def test_existing_noindexed_canonical_target_generates_confirmed_finding():
    source = _page("https://example.com/source", canonical="https://example.com/target")
    target = _page("https://example.com/target", canonical="https://example.com/target", robots="noindex")

    summary = await validate_canonical_targets(FakeClient({}), [source, target], RobotsPolicy("https://example.com/robots.txt", "missing", 404))
    finding = next(item for item in build_findings([source, target]) if item["rule"] == "canonical_target_noindex")

    assert source["canonical_target_state"] == "target_noindexed"
    assert source["canonical_target_evidence_source"] == "crawl"
    assert finding["priority"] == "high"
    assert finding["canonical_target_url"] == "https://example.com/target"
    assert summary["state_counts"]["target_noindexed"] == 1


@pytest.mark.asyncio
async def test_redirecting_canonical_target_preserves_location():
    source = _page("https://example.com/source", canonical="https://example.com/old")
    client = FakeClient({
        "https://example.com/old": _response(
            "https://example.com/old",
            301,
            headers={"content-type": "text/html", "location": "/new"},
        )
    })

    await validate_canonical_targets(client, [source], RobotsPolicy("https://example.com/robots.txt", "missing", 404))
    finding = next(item for item in build_findings([source]) if item["rule"] == "canonical_target_redirect")

    assert source["canonical_target_state"] == "target_redirected"
    assert source["canonical_target_redirect_location"] == "https://example.com/new"
    assert finding["current_value"].startswith("https://example.com/old")


@pytest.mark.asyncio
async def test_failed_canonical_target_is_high_priority():
    source = _page("https://example.com/source", canonical="https://example.com/missing")
    client = FakeClient({"https://example.com/missing": _response("https://example.com/missing", 404)})

    await validate_canonical_targets(client, [source], RobotsPolicy("https://example.com/robots.txt", "missing", 404))
    finding = next(item for item in build_findings([source]) if item["rule"] == "canonical_target_failed")

    assert source["canonical_target_state"] == "target_failed"
    assert source["canonical_target_status_code"] == 404
    assert finding["priority"] == "high"


@pytest.mark.asyncio
async def test_target_canonical_back_to_source_is_a_loop():
    source = _page("https://example.com/source", canonical="https://example.com/target")
    target_body = '<html><head><title>Target</title><link rel="canonical" href="https://example.com/source"></head><body><h1>Target</h1></body></html>'
    client = FakeClient({"https://example.com/target": _response("https://example.com/target", 200, body=target_body)})

    await validate_canonical_targets(client, [source], RobotsPolicy("https://example.com/robots.txt", "missing", 404))
    finding = next(item for item in build_findings([source]) if item["rule"] == "canonical_loop")

    assert source["canonical_target_state"] == "canonical_loop"
    assert source["canonical_target_declared_canonical"] == "https://example.com/source"
    assert finding["priority"] == "high"


@pytest.mark.asyncio
async def test_target_canonical_to_third_url_is_a_chain():
    source = _page("https://example.com/source", canonical="https://example.com/target")
    target_body = '<html><head><title>Target</title><link rel="canonical" href="https://example.com/preferred"></head><body><h1>Target</h1></body></html>'
    client = FakeClient({"https://example.com/target": _response("https://example.com/target", 200, body=target_body)})

    await validate_canonical_targets(client, [source], RobotsPolicy("https://example.com/robots.txt", "missing", 404))

    assert source["canonical_target_state"] == "canonical_chain"
    assert any(item["rule"] == "canonical_chain" for item in build_findings([source]))


@pytest.mark.asyncio
async def test_cross_domain_canonical_is_non_scoring_verification_task():
    source = _page("https://example.com/source", canonical="https://other.example/preferred")
    client = FakeClient({})

    await validate_canonical_targets(client, [source], RobotsPolicy("https://example.com/robots.txt", "missing", 404))
    finding = next(item for item in build_findings([source]) if item["rule"] == "canonical_cross_domain")

    assert client.calls == []
    assert source["canonical_target_state"] == "cross_domain_needs_verification"
    assert finding["priority"] == "low"
    assert finding["evidence_status"] == "needs_verification"
    assert finding["verification_state"] == "needs_verification"


@pytest.mark.asyncio
async def test_deadline_limit_does_not_create_a_false_problem():
    source = _page("https://example.com/source", canonical="https://example.com/target")

    await validate_canonical_targets(
        FakeClient({}),
        [source],
        RobotsPolicy("https://example.com/robots.txt", "missing", 404),
        deadline=time.monotonic() - 1,
    )

    assert source["canonical_target_state"] == "not_checked_due_to_deadline"
    assert not any(item["rule"].startswith("canonical_target") for item in build_findings([source]))


@pytest.mark.asyncio
async def test_valid_target_does_not_generate_problem():
    source = _page("https://example.com/source", canonical="https://example.com/target")
    client = FakeClient({"https://example.com/target": _response("https://example.com/target", 200)})

    await validate_canonical_targets(client, [source], RobotsPolicy("https://example.com/robots.txt", "missing", 404))

    assert source["canonical_target_state"] == "valid"
    assert not any(item["rule"].startswith("canonical_") and item["rule"] != "canonical_missing" for item in build_findings([source]))
