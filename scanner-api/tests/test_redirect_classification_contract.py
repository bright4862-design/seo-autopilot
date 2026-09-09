from contextlib import asynccontextmanager
import socket

import httpx
import pytest

from app.extract import extract_page
from app.robots_policy import RobotsPolicy
from app.redirect_validation import summarize_redirect_evidence
from app.scanner import (
    build_findings,
    fetch_and_extract,
    group_findings,
    merge_duplicate_page_evidence,
)


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
    assert evidence["classification"] == "redirect_to_usable_page"


@pytest.mark.asyncio
async def test_deep_url_redirecting_to_homepage_is_wrong_destination_even_when_homepage_is_200(policy):
    source = "https://example.com/property-management-in-baltimore/mt-vernon"
    homepage = "https://example.com/"
    homepage_html = (
        '<html><head><title>Property Management</title>'
        '<link rel="canonical" href="https://example.com/"></head>'
        '<body><h1>Property Management</h1><p>Homepage content.</p></body></html>'
    )
    client = FakeClient({
        source: _response(source, 301, location="/"),
        homepage: _response(homepage, 200, body=homepage_html),
    })

    page = await fetch_and_extract(client, source, DISCOVERY_INTERNAL, robots_policy=policy)
    findings = build_findings([page])

    assert page["redirect_outcome"] == "redirect_to_wrong_destination"
    wrong = next(item for item in findings if item["rule"] == "redirect_wrong_destination")
    assert wrong["verification_state"] == "verified"
    assert wrong["redirect_fetch_evidence"]["final_status"] == 200
    assert wrong["redirect_fetch_evidence"]["final_url"] == homepage
    assert wrong["redirect_fetch_evidence"]["classification"] == "redirect_to_wrong_destination"
    assert "redirect_destination_failed" not in {item["rule"] for item in findings}


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
    assert evidence["classification"] == "redirect_destination_unusable"


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
async def test_redirect_destination_timeout_is_unverified_and_not_fabricated_as_confirmed_http_failure(policy):
    client = FakeClient({
        "https://example.com/old": _response("https://example.com/old", 301, location="/slow"),
        "https://example.com/slow": httpx.ReadTimeout("timed out"),
    })

    page = await fetch_and_extract(client, "https://example.com/old", DISCOVERY_INTERNAL, robots_policy=policy)
    findings = build_findings([page])

    assert page["redirect_outcome"] == "redirect_destination_unverified"
    assert page["redirect_state"] == "redirect_destination_unverified"
    assert "redirect_destination_failed" not in {finding["rule"] for finding in findings}
    finding = next(finding for finding in findings if finding["rule"] == "redirect_destination_unverified")
    assert finding["verification_state"] == "needs_verification"
    assert finding["non_scoring"] is True
    assert finding["redirect_fetch_evidence"]["fetch_error"]
    assert finding["redirect_fetch_evidence"]["final_status"] == 0
    assert finding["redirect_fetch_evidence"]["classification"] == "redirect_destination_unverified"


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
    rules = _rules(page)
    assert "sitemap_redirect" in rules
    assert "redirect_destination_failed" not in rules
    assert "redirect_wrong_destination" not in rules
    description = next(item for item in build_findings([page]) if item["rule"] == "missing_meta_description")
    assert description["affected_pages"] == ["/about/"]


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


def test_redirect_repairs_do_not_merge_missing_h1_meta_image_or_canonical_repairs():
    html = (
        '<html><head><title>Service page</title></head>'
        '<body><p>Useful content.</p><img src="/team.jpg"></body></html>'
    )
    page = extract_page(
        html,
        "https://example.com/service",
        "https://example.com/service",
        200,
        "text/html",
        DISCOVERY_INTERNAL,
    )
    findings = build_findings([page])
    grouped = group_findings(findings)
    rules = {item["rule"] for item in grouped}

    assert "missing_h1" in rules
    assert "missing_meta_description" in rules
    assert "image_alt_text" in rules
    assert "canonical_missing" in rules
    assert not any(rule.startswith("redirect_destination") for rule in rules)


def test_wrong_destination_evidence_survives_final_url_dedup_against_retained_homepage():
    homepage_html = (
        '<html><head><title>Home</title><link rel="canonical" href="https://example.com/"></head>'
        '<body><h1>Home</h1><p>Useful homepage content.</p></body></html>'
    )
    homepage = extract_page(
        homepage_html,
        "https://example.com/",
        "https://example.com/",
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )
    duplicate = extract_page(
        homepage_html,
        "https://example.com/property-management-in-baltimore/mt-vernon",
        "https://example.com/",
        200,
        "text/html",
        DISCOVERY_INTERNAL,
    )
    duplicate.update({
        "redirect_state": "single_redirect",
        "redirect_outcome": "redirect_to_wrong_destination",
        "redirect_hop_count": 1,
        "redirect_source_url": "https://example.com/property-management-in-baltimore/mt-vernon",
        "redirect_source_path": "/property-management-in-baltimore/mt-vernon",
        "redirect_destination_url": "https://example.com/",
        "redirect_destination_status_code": 200,
        "redirect_destination_indexability_state": "Indexable",
        "redirect_chain": [
            "https://example.com/property-management-in-baltimore/mt-vernon",
            "https://example.com/",
        ],
        "redirect_fetch_evidence": {
            "requested_url": "https://example.com/property-management-in-baltimore/mt-vernon",
            "redirect_chain": [{
                "url": "https://example.com/property-management-in-baltimore/mt-vernon",
                "status": 301,
                "location": "https://example.com/",
            }],
            "final_url": "https://example.com/",
            "final_status": 200,
            "final_content_type": "text/html",
            "body_bytes": len(homepage_html.encode("utf-8")),
            "html_parse_ok": True,
            "fetch_error": None,
            "robots_status": "Indexable",
            "canonical_url": "https://example.com/",
            "noindex": False,
            "classification": "redirect_to_wrong_destination",
        },
    })

    merge_duplicate_page_evidence(homepage, duplicate)
    findings = build_findings([homepage])

    wrong = next(item for item in findings if item["rule"] == "redirect_wrong_destination")
    assert wrong["affected_pages"] == ["/property-management-in-baltimore/mt-vernon"]
    assert wrong["redirect_fetch_evidence"]["final_url"] == "https://example.com/"

@pytest.mark.asyncio
async def test_usable_redirect_destination_keeps_its_own_content_findings_on_final_url(policy):
    final_html = (
        '<html><head><title>Final service page</title></head>'
        '<body><p>Useful final-page content.</p><img src="/hero.jpg"></body></html>'
    )
    client = FakeClient({
        "https://example.com/old-service": _response(
            "https://example.com/old-service", 301, location="/final-service"
        ),
        "https://example.com/final-service": _response(
            "https://example.com/final-service", 200, body=final_html
        ),
    })

    page = await fetch_and_extract(
        client,
        "https://example.com/old-service",
        DISCOVERY_INTERNAL,
        robots_policy=policy,
    )
    findings = build_findings([page])

    assert any(
        item["rule"] == "internal_link_redirect" and item["affected_pages"] == ["/old-service"]
        for item in findings
    )
    for rule in {"missing_meta_description", "missing_h1", "canonical_missing", "image_alt_text"}:
        finding = next(item for item in findings if item["rule"] == rule)
        assert finding["affected_pages"] == ["/final-service"]
    assert not any(item["rule"] == "sitemap_indexability_conflict" for item in findings)



def _wrong_destination_alias(source_path: str) -> dict:
    homepage_html = (
        '<html><head><title>Home</title><link rel="canonical" href="https://example.com/"></head>'
        '<body><h1>Home</h1><p>Useful homepage content.</p></body></html>'
    )
    source = f"https://example.com{source_path}"
    page = extract_page(
        homepage_html,
        source,
        "https://example.com/",
        200,
        "text/html",
        DISCOVERY_INTERNAL,
    )
    page.update({
        "redirect_state": "single_redirect",
        "redirect_outcome": "redirect_to_wrong_destination",
        "redirect_hop_count": 1,
        "redirect_source_url": source,
        "redirect_source_path": source_path,
        "redirect_destination_url": "https://example.com/",
        "redirect_destination_status_code": 200,
        "redirect_destination_indexability_state": "Indexable",
        "redirect_destination_indexable": True,
        "redirect_chain": [source, "https://example.com/"],
        "redirect_fetch_evidence": {
            "requested_url": source,
            "redirect_chain": [{"url": source, "status": 301, "location": "https://example.com/"}],
            "final_url": "https://example.com/",
            "final_status": 200,
            "final_content_type": "text/html",
            "body_bytes": len(homepage_html.encode("utf-8")),
            "html_parse_ok": True,
            "fetch_error": None,
            "robots_status": "Indexable",
            "canonical_url": "https://example.com/",
            "noindex": False,
            "classification": "redirect_to_wrong_destination",
        },
    })
    return page


def test_redirect_summary_keeps_complete_alias_totals_with_bounded_examples():
    homepage = extract_page(
        '<html><head><title>Home</title></head><body><h1>Home</h1></body></html>',
        "https://example.com/",
        "https://example.com/",
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )
    for index in range(25):
        merge_duplicate_page_evidence(homepage, _wrong_destination_alias(f"/locations/deprecated-{index}"))

    assert len(homepage["redirect_aliases"]) == 20
    assert homepage["redirect_alias_total"] == 25

    summary = summarize_redirect_evidence([homepage])
    assert summary["redirected_pages"] == 25
    assert summary["outcome_counts"] == {"redirect_to_wrong_destination": 25}
    assert summary["state_counts"] == {"single_redirect": 25}
    assert summary["internal_link_redirects"] == 25
    assert len(summary["redirects"]) == 20
    assert len(summary["representative_redirects"]) == 20


def test_redirect_summary_is_order_independent_when_final_url_deduplicates():
    homepage = extract_page(
        '<html><head><title>Home</title></head><body><h1>Home</h1></body></html>',
        "https://example.com/",
        "https://example.com/",
        200,
        "text/html",
        {"discovered_from": ["seed"], "source_pages": [], "link_text_samples": []},
    )
    alias = _wrong_destination_alias("/locations/deprecated")

    retained_final = dict(homepage)
    merge_duplicate_page_evidence(retained_final, alias)
    summary_final_first = summarize_redirect_evidence([retained_final])

    retained_alias = dict(alias)
    merge_duplicate_page_evidence(retained_alias, homepage)
    summary_alias_first = summarize_redirect_evidence([retained_alias])

    for key in ("redirected_pages", "state_counts", "outcome_counts", "internal_link_redirects"):
        assert summary_final_first[key] == summary_alias_first[key]
    assert summary_final_first["redirected_pages"] == 1
