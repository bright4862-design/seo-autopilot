from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket
import subprocess

import httpx
import pytest

from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.robots_policy import RobotsPolicy
from app.scan_job import build_local_review
from app.scanner import build_findings, fetch_and_extract, group_findings


ORIGIN = "https://example.com"
DISCOVERY_INTERNAL = {
    "discovered_from": ["internal_link"],
    "source_pages": ["/source"],
    "link_text_samples": ["Legacy destination"],
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
    monkeypatch.setattr("app.redirect_validation.is_public_http_url", lambda _url: True)


@pytest.fixture
def policy():
    return RobotsPolicy("https://example.com/robots.txt", "missing", 404)


def _response(url, status=200, *, location="", body=None, content_type="text/html; charset=utf-8", headers=None):
    response_headers = {"content-type": content_type}
    if location:
        response_headers["location"] = location
    if headers:
        response_headers.update(headers)
    html = body if body is not None else (
        f'<html><head><title>Page</title><link rel="canonical" href="{url}"></head>'
        '<body><h1>Page</h1><p>Useful HTML content.</p></body></html>'
    )
    return httpx.Response(
        status,
        headers=response_headers,
        stream=httpx.ByteStream(html.encode("utf-8")),
        request=httpx.Request("GET", url),
    )


def _html(url: str, *, title: str, h1: str, description: str = "") -> str:
    meta = f'<meta name="description" content="{description}">' if description else ""
    return (
        f'<html><head><title>{title}</title>{meta}<link rel="canonical" href="{url}"></head>'
        f'<body><h1>{h1}</h1><p>{description or title} information and navigation.</p></body></html>'
    )


def _assert_persisted_customer_output(page: dict, expected_url: str) -> None:
    raw = build_findings(
        [page],
        identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
        scan_origin=ORIGIN,
    )
    result = {
        "success": True,
        "website_url": ORIGIN,
        "crawl_scope": {"requested_origin": ORIGIN},
        "pages": [page],
        "crawled_pages": [page],
        "pages_found": 1,
        "pages_crawled": 1,
        "raw_findings": raw,
        "findings": group_findings(raw),
    }
    completed = subprocess.run(
        ["node", "tests/helpers/assertPublishedEvidenceOutput.mjs"],
        input=json.dumps({
            "scan": result,
            "review": build_local_review(result),
            "expectedUrls": [expected_url],
            "expectedRule": "redirect_wrong_destination",
            "expectedEligible": 1,
        }),
        text=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2],
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.asyncio
async def test_related_hub_redirect_is_usable_not_wrong_destination(policy):
    source = "https://example.com/property-management-in-baltimore/mt-vernon"
    destination = "https://example.com/property-management/"
    client = FakeClient({
        source: _response(source, 301, location="/property-management/"),
        destination: _response(
            destination,
            200,
            body=_html(
                destination,
                title="Property Management Services",
                h1="Property Management",
                description="Property management services and local teams.",
            ),
        ),
    })
    discovery = {
        **DISCOVERY_INTERNAL,
        "link_text_samples": ["Mt Vernon property management"],
    }

    page = await fetch_and_extract(client, source, discovery, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_to_usable_page"
    assert page["redirect_fetch_evidence"]["meaning_evidence"]["state"] == "verified_related"
    assert "property" in page["redirect_fetch_evidence"]["meaning_evidence"]["shared_terms"]
    assert "redirect_wrong_destination" not in {row["rule"] for row in build_findings([page])}


@pytest.mark.asyncio
async def test_unrelated_section_redirect_is_wrong_destination_even_when_200(policy):
    source = "https://example.com/property-management-in-baltimore/mt-vernon"
    destination = "https://example.com/blog/"
    client = FakeClient({
        source: _response(source, 301, location="/blog/"),
        destination: _response(
            destination,
            200,
            body=_html(
                destination,
                title="Company News and Blog",
                h1="Latest articles",
                description="News, announcements and company stories.",
            ),
        ),
    })
    discovery = {
        **DISCOVERY_INTERNAL,
        "link_text_samples": ["Mt Vernon property management"],
    }

    page = await fetch_and_extract(client, source, discovery, robots_policy=policy)
    findings = build_findings([page])

    assert page["redirect_outcome"] == "redirect_to_wrong_destination"
    meaning = page["redirect_fetch_evidence"]["meaning_evidence"]
    assert meaning["state"] == "verified_mismatch"
    assert meaning["reason"] == "specific_source_to_unrelated_generic_destination"
    wrong = next(row for row in findings if row["rule"] == "redirect_wrong_destination")
    assert wrong["verification_state"] == "verified"
    assert wrong["redirect_fetch_evidence"]["classification"] == "redirect_to_wrong_destination"
    _assert_persisted_customer_output(page, source)


@pytest.mark.asyncio
async def test_explicit_home_intent_can_legitimately_redirect_to_homepage(policy):
    source = "https://example.com/legacy/home"
    destination = "https://example.com/"
    client = FakeClient({
        source: _response(source, 301, location="/"),
        destination: _response(
            destination,
            200,
            body=_html(
                destination,
                title="Example Home",
                h1="Welcome to Example",
                description="Homepage for Example services and navigation.",
            ),
        ),
    })
    discovery = {
        **DISCOVERY_INTERNAL,
        "link_text_samples": ["Home"],
    }

    page = await fetch_and_extract(client, source, discovery, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_to_usable_page"
    meaning = page["redirect_fetch_evidence"]["meaning_evidence"]
    assert meaning["state"] == "verified_related"
    assert meaning["reason"] == "explicit_home_intent"
    assert "redirect_wrong_destination" not in {row["rule"] for row in build_findings([page])}


@pytest.mark.asyncio
async def test_access_challenge_destination_remains_unverified_not_unusable(policy):
    source = "https://example.com/old"
    destination = "https://example.com/protected"
    challenge = (
        "<html><head><title>Checking your browser</title></head>"
        "<body><h1>Verify you are human</h1><p>Checking your browser before accessing the site.</p></body></html>"
    )
    client = FakeClient({
        source: _response(source, 301, location="/protected"),
        destination: _response(
            destination,
            200,
            body=challenge,
            headers={"server": "cloudflare", "cf-ray": "test-ray"},
        ),
    })

    page = await fetch_and_extract(client, source, DISCOVERY_INTERNAL, robots_policy=policy)
    findings = build_findings([page])

    assert page["redirect_outcome"] == "redirect_destination_unverified"
    meaning = page["redirect_fetch_evidence"]["meaning_evidence"]
    assert meaning["state"] == "not_verified"
    assert meaning["reason"] == "destination_access_unverified"
    assert not any(row["rule"] == "redirect_destination_failed" for row in findings)


@pytest.mark.asyncio
async def test_non_html_200_destination_is_unusable_not_nonindexable(policy):
    source = "https://example.com/old-feed"
    destination = "https://example.com/feed.json"
    client = FakeClient({
        source: _response(source, 301, location="/feed.json"),
        destination: _response(
            destination,
            200,
            body='{"status":"ok"}',
            content_type="application/json",
        ),
    })

    page = await fetch_and_extract(client, source, DISCOVERY_INTERNAL, robots_policy=policy)

    assert page["redirect_outcome"] == "redirect_destination_unusable"
    evidence = page["redirect_fetch_evidence"]
    assert evidence["html_parse_ok"] is False
    assert evidence["classification"] == "redirect_destination_unusable"
    assert evidence["meaning_evidence"]["reason"] == "destination_not_usable_html"
