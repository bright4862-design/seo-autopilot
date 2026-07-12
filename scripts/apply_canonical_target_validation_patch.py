from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scanner-api/app/scanner.py"
MODULE = ROOT / "scanner-api/app/canonical_validation.py"
TEST = ROOT / "scanner-api/tests/test_canonical_target_validation.py"

module_content = '''from __future__ import annotations

import asyncio
import time
from collections import Counter
from urllib.parse import urldefrag, urljoin, urlparse

from .extract import extract_page
from .robots_policy import SCANNER_USER_AGENT, SEARCH_USER_AGENT, annotate_robots_evidence
from .security import is_public_http_url


CANONICAL_TARGET_EVIDENCE_VERSION = "canonical_target_evidence_v1"
DEFAULT_MAX_TARGETS = 20
DEFAULT_CONCURRENCY = 4
DEFAULT_REQUEST_TIMEOUT_SECONDS = 8.0


def _normalize_url(value: str) -> str:
    raw, _ = urldefrag(str(value or "").strip())
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), path=path, fragment="").geturl()


def _origin_key(value: str) -> tuple[str, int | None]:
    parsed = urlparse(str(value or ""))
    return ((parsed.hostname or "").lower(), parsed.port)


def _page_identity_urls(page: dict) -> set[str]:
    return {
        normalized
        for normalized in (
            _normalize_url(page.get("url")),
            _normalize_url(page.get("final_url")),
        )
        if normalized
    }


def _evidence_from_page(page: dict, target: str, source: str = "crawl") -> dict:
    status_code = int(page.get("status_code") or 0)
    fetch_error = str(page.get("fetch_error") or "")
    indexability_state = str(page.get("indexability_state") or "")
    target_canonical = _normalize_url(page.get("canonical"))

    if indexability_state == "Blocked by robots.txt" or fetch_error == "blocked_by_robots_txt":
        state = "target_blocked_by_robots"
    elif 300 <= status_code < 400:
        state = "target_redirected"
    elif status_code >= 400 or fetch_error:
        state = "target_failed"
    elif indexability_state == "Noindexed":
        state = "target_noindexed"
    elif 200 <= status_code < 300 and page.get("indexable") is True:
        state = "valid"
    else:
        state = "unknown_access_limited"

    return {
        "state": state,
        "target_url": target,
        "status_code": status_code,
        "indexability_state": indexability_state,
        "fetch_error": fetch_error,
        "location": str(page.get("redirect_location") or ""),
        "target_canonical": target_canonical,
        "evidence_source": source,
    }


async def _fetch_target(client, target: str, robots_policy, deadline: float | None) -> dict:
    if not is_public_http_url(target):
        return {
            "state": "invalid_target",
            "target_url": target,
            "status_code": 0,
            "indexability_state": "Unknown",
            "fetch_error": "invalid_or_non_public_canonical_target",
            "location": "",
            "target_canonical": "",
            "evidence_source": "validation",
        }

    googlebot_allowed = robots_policy.allowed(SEARCH_USER_AGENT, target)
    scanner_allowed = robots_policy.allowed(SCANNER_USER_AGENT, target)
    if googlebot_allowed is False:
        return {
            "state": "target_blocked_by_robots",
            "target_url": target,
            "status_code": 0,
            "indexability_state": "Blocked by robots.txt",
            "fetch_error": "",
            "location": "",
            "target_canonical": "",
            "evidence_source": "robots_txt",
        }
    if scanner_allowed is False:
        return {
            "state": "unknown_access_limited",
            "target_url": target,
            "status_code": 0,
            "indexability_state": "Unknown",
            "fetch_error": "scanner_blocked_by_robots_txt",
            "location": "",
            "target_canonical": "",
            "evidence_source": "robots_txt",
        }

    remaining = None if deadline is None else deadline - time.monotonic()
    if remaining is not None and remaining <= 0:
        return {
            "state": "not_checked_due_to_deadline",
            "target_url": target,
            "status_code": 0,
            "indexability_state": "Unknown",
            "fetch_error": "",
            "location": "",
            "target_canonical": "",
            "evidence_source": "budget",
        }

    timeout = DEFAULT_REQUEST_TIMEOUT_SECONDS if remaining is None else max(0.1, min(DEFAULT_REQUEST_TIMEOUT_SECONDS, remaining))
    try:
        response = await asyncio.wait_for(client.get(target), timeout=timeout)
    except Exception as exc:
        return {
            "state": "target_failed",
            "target_url": target,
            "status_code": 0,
            "indexability_state": "Failed",
            "fetch_error": str(exc)[:180],
            "location": "",
            "target_canonical": "",
            "evidence_source": "validation",
        }

    status_code = int(getattr(response, "status_code", 0) or 0)
    if 300 <= status_code < 400:
        location = str(response.headers.get("location") or "")
        return {
            "state": "target_redirected",
            "target_url": target,
            "status_code": status_code,
            "indexability_state": "Redirected",
            "fetch_error": "",
            "location": urljoin(target, location) if location else "",
            "target_canonical": "",
            "evidence_source": "validation",
        }
    if status_code >= 400:
        return {
            "state": "target_failed",
            "target_url": target,
            "status_code": status_code,
            "indexability_state": "Failed",
            "fetch_error": "",
            "location": "",
            "target_canonical": "",
            "evidence_source": "validation",
        }

    content_type = str(response.headers.get("content-type") or "")
    if "html" not in content_type and content_type:
        return {
            "state": "unknown_access_limited",
            "target_url": target,
            "status_code": status_code,
            "indexability_state": "Unknown",
            "fetch_error": "non_html_canonical_target",
            "location": "",
            "target_canonical": "",
            "evidence_source": "validation",
        }

    target_page = extract_page(
        str(getattr(response, "text", "") or ""),
        target,
        str(getattr(response, "url", target) or target),
        status_code,
        content_type,
        {"discovered_from": ["canonical_target"], "source_pages": [], "link_text_samples": []},
        response_headers={"x-robots-tag": response.headers.get_list("x-robots-tag")},
    )
    annotate_robots_evidence(target_page, robots_policy, target)
    return _evidence_from_page(target_page, target, "validation")


def _apply_evidence(page: dict, target: str, evidence: dict) -> None:
    state = str(evidence.get("state") or "unknown_access_limited")
    target_canonical = _normalize_url(evidence.get("target_canonical"))
    if state == "valid" and target_canonical:
        if target_canonical in _page_identity_urls(page):
            state = "canonical_loop"
        elif target_canonical != target:
            state = "canonical_chain"

    page.update({
        "canonical_target_validation_version": CANONICAL_TARGET_EVIDENCE_VERSION,
        "canonical_target_url": target,
        "canonical_target_state": state,
        "canonical_target_status_code": int(evidence.get("status_code") or 0),
        "canonical_target_indexability_state": str(evidence.get("indexability_state") or "Unknown"),
        "canonical_target_fetch_error": str(evidence.get("fetch_error") or ""),
        "canonical_target_redirect_location": str(evidence.get("location") or ""),
        "canonical_target_declared_canonical": target_canonical,
        "canonical_target_evidence_source": str(evidence.get("evidence_source") or "unknown"),
        "canonical_target_checked": state not in {"not_checked_due_to_deadline", "not_checked_due_to_limit"},
    })


async def validate_canonical_targets(
    client,
    pages: list[dict],
    robots_policy,
    *,
    deadline: float | None = None,
    max_targets: int = DEFAULT_MAX_TARGETS,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict:
    page_by_url: dict[str, dict] = {}
    for page in pages:
        for identity in _page_identity_urls(page):
            page_by_url.setdefault(identity, page)

    same_origin_sources: dict[str, list[dict]] = {}
    declaration_count = 0
    for page in pages:
        if str(page.get("canonical_status") or "") != "canonical_to_different_url":
            continue
        target = _normalize_url(page.get("canonical"))
        if not target:
            continue
        declaration_count += 1
        source_url = _normalize_url(page.get("final_url") or page.get("url"))
        if not source_url or _origin_key(source_url) != _origin_key(target):
            _apply_evidence(page, target, {
                "state": "cross_domain_needs_verification",
                "target_url": target,
                "status_code": 0,
                "indexability_state": "Unknown",
                "fetch_error": "",
                "location": "",
                "target_canonical": "",
                "evidence_source": "declaration_only",
            })
            continue
        same_origin_sources.setdefault(target, []).append(page)

    target_evidence: dict[str, dict] = {}
    pending: list[str] = []
    for target in same_origin_sources:
        existing = page_by_url.get(target)
        if existing is not None:
            target_evidence[target] = _evidence_from_page(existing, target)
        else:
            pending.append(target)

    selected = pending[: max(0, int(max_targets))]
    for target in pending[len(selected):]:
        target_evidence[target] = {
            "state": "not_checked_due_to_limit",
            "target_url": target,
            "status_code": 0,
            "indexability_state": "Unknown",
            "fetch_error": "",
            "location": "",
            "target_canonical": "",
            "evidence_source": "budget",
        }

    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    async def inspect(target: str) -> tuple[str, dict]:
        async with semaphore:
            return target, await _fetch_target(client, target, robots_policy, deadline)

    if selected:
        for target, evidence in await asyncio.gather(*(inspect(target) for target in selected)):
            target_evidence[target] = evidence

    for target, sources in same_origin_sources.items():
        evidence = target_evidence.get(target) or {
            "state": "unknown_access_limited",
            "target_url": target,
            "status_code": 0,
            "indexability_state": "Unknown",
            "fetch_error": "",
            "location": "",
            "target_canonical": "",
            "evidence_source": "unknown",
        }
        for page in sources:
            _apply_evidence(page, target, evidence)

    states = Counter(
        str(page.get("canonical_target_state") or "")
        for page in pages
        if page.get("canonical_target_state")
    )
    issue_states = {
        "target_redirected",
        "target_failed",
        "target_noindexed",
        "target_blocked_by_robots",
        "canonical_chain",
        "canonical_loop",
        "cross_domain_needs_verification",
        "invalid_target",
    }
    return {
        "version": CANONICAL_TARGET_EVIDENCE_VERSION,
        "pages_declaring_other_canonical": declaration_count,
        "unique_same_origin_targets": len(same_origin_sources),
        "targets_fetched": sum(1 for evidence in target_evidence.values() if evidence.get("evidence_source") == "validation"),
        "state_counts": dict(sorted(states.items())),
        "representative_issues": [
            {
                "page": page.get("path") or page.get("url"),
                "target": page.get("canonical_target_url"),
                "state": page.get("canonical_target_state"),
            }
            for page in pages
            if page.get("canonical_target_state") in issue_states
        ][:20],
    }
'''


test_content = '''import time

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


def _response(url: str, status: int, *, body="<html><head><title>Target</title></head><body><h1>Target</h1></body></html>", headers=None):
    return httpx.Response(status, text=body, headers=headers or {"content-type": "text/html"}, request=httpx.Request("GET", url))


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
'''

MODULE.write_text(module_content)
TEST.write_text(test_content)

scanner = SCANNER.read_text()

replacements = [
    (
        "from .artifact_filter import MAX_ARTIFACT_EVIDENCE, is_artifact_url, record_artifact\n",
        "from .artifact_filter import MAX_ARTIFACT_EVIDENCE, is_artifact_url, record_artifact\nfrom .canonical_validation import validate_canonical_targets\n",
    ),
    (
        "        workers = [asyncio.create_task(worker()) for _ in range(max(1, concurrency))]\n        await asyncio.gather(*workers)\n\n    findings = build_findings(pages)\n",
        "        workers = [asyncio.create_task(worker()) for _ in range(max(1, concurrency))]\n        await asyncio.gather(*workers)\n        canonical_target_evidence = await validate_canonical_targets(\n            client,\n            pages,\n            robots_policy,\n            deadline=deadline,\n        )\n\n    findings = build_findings(pages)\n",
    ),
    (
        '        "robots_txt_evidence": robots_policy.evidence(),\n        "scan_mode": scan_mode,\n',
        '        "robots_txt_evidence": robots_policy.evidence(),\n        "canonical_target_evidence": canonical_target_evidence,\n        "scan_mode": scan_mode,\n',
    ),
    (
        '            "crawl_scope": dict(scope_evidence),\n            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n',
        '            "crawl_scope": dict(scope_evidence),\n            "canonical_target_evidence": canonical_target_evidence,\n            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n',
    ),
    (
        '        if str(page.get("fetch_error") or "").startswith("blocked_"):\n',
        '        canonical_finding = canonical_target_finding(page)\n        if canonical_finding is not None:\n            findings.append(canonical_finding)\n        if str(page.get("fetch_error") or "").startswith("blocked_"):\n',
    ),
    (
        'TEMPLATE_RULES = {"client_rendering", "canonical_missing", "schema", "missing_h1", "multiple_h1", "image_alt_text", "missing_meta_description", "sitemap_indexability_conflict"}\n',
        'TEMPLATE_RULES = {"client_rendering", "canonical_missing", "canonical_target_redirect", "canonical_target_failed", "canonical_target_noindex", "canonical_target_blocked", "canonical_chain", "canonical_loop", "canonical_cross_domain", "schema", "missing_h1", "multiple_h1", "image_alt_text", "missing_meta_description", "sitemap_indexability_conflict"}\n',
    ),
    (
        '    if rule == "canonical_missing":\n        return f"Add canonical URLs across {fam} templates"\n    if rule == "sitemap_indexability_conflict":\n',
        '    if rule == "canonical_missing":\n        return f"Add canonical URLs across {fam} templates"\n    if rule == "canonical_target_redirect":\n        return "Update canonicals that point to redirects"\n    if rule == "canonical_target_failed":\n        return "Fix canonicals that point to unavailable pages"\n    if rule == "canonical_target_noindex":\n        return "Fix canonicals that point to noindexed pages"\n    if rule == "canonical_target_blocked":\n        return "Review canonicals that point to robots-blocked pages"\n    if rule == "canonical_chain":\n        return "Replace canonical chains with the final preferred URL"\n    if rule == "canonical_loop":\n        return "Remove canonical loops"\n    if rule == "canonical_cross_domain":\n        return "Verify cross-domain canonical URLs"\n    if rule == "sitemap_indexability_conflict":\n',
    ),
]

for old, new in replacements:
    if old not in scanner:
        raise SystemExit(f"Expected scanner block not found:\n{old}")
    scanner = scanner.replace(old, new, 1)

helper = '''\n\ndef canonical_target_finding(page: dict) -> dict | None:\n    state = str(page.get("canonical_target_state") or "")\n    target = str(page.get("canonical_target_url") or page.get("canonical") or "")\n    status_code = int(page.get("canonical_target_status_code") or 0)\n    redirect_location = str(page.get("canonical_target_redirect_location") or "")\n    target_canonical = str(page.get("canonical_target_declared_canonical") or "")\n    mapping = {\n        "target_redirected": (\n            "canonical_target_redirect",\n            "medium",\n            "Update a canonical URL that points to a redirect",\n            "The declared canonical URL redirects instead of resolving directly.",\n            "Point the canonical directly to the final 200-status preferred URL.",\n        ),\n        "target_failed": (\n            "canonical_target_failed",\n            "high",\n            "Fix a canonical URL that points to an unavailable page",\n            "The declared canonical target failed to load or returned an error.",\n            "Choose a live, indexable preferred URL and update the canonical reference.",\n        ),\n        "target_noindexed": (\n            "canonical_target_noindex",\n            "high",\n            "Fix a canonical URL that points to a noindexed page",\n            "The page asks search engines to consolidate signals into a target that is explicitly noindexed.",\n            "Use an indexable preferred URL or remove the conflicting noindex directive from the intended target.",\n        ),\n        "target_blocked_by_robots": (\n            "canonical_target_blocked",\n            "medium",\n            "Review a canonical URL that points to a robots-blocked page",\n            "Googlebot is blocked from crawling the declared canonical target, so the consolidation signal may be hard to verify.",\n            "Confirm the intended preferred URL and allow Googlebot to crawl it when appropriate.",\n        ),\n        "canonical_chain": (\n            "canonical_chain",\n            "medium",\n            "Replace a canonical chain with the final preferred URL",\n            "The declared canonical target itself points to another canonical URL.",\n            "Point the source page directly to the final preferred canonical destination.",\n        ),\n        "canonical_loop": (\n            "canonical_loop",\n            "high",\n            "Remove a canonical loop",\n            "The source and target canonical declarations point back to each other.",\n            "Choose one preferred URL and make every duplicate point directly to it without a loop.",\n        ),\n        "cross_domain_needs_verification": (\n            "canonical_cross_domain",\n            "low",\n            "Verify a cross-domain canonical URL",\n            "This page declares a preferred URL on another domain. That can be intentional, but ownership and matching content require confirmation.",\n            "Confirm both domains are controlled by the same organization and that the external URL is the intended equivalent page.",\n        ),\n        "invalid_target": (\n            "canonical_target_failed",\n            "high",\n            "Fix an invalid canonical target",\n            "The declared canonical target is invalid or does not resolve to a public HTTP URL.",\n            "Replace it with a valid absolute HTTPS URL for the preferred page.",\n        ),\n    }\n    details = mapping.get(state)\n    if details is None:\n        return None\n    rule, priority, title, explanation, recommendation = details\n    current_parts = [target]\n    if status_code:\n        current_parts.append(f"HTTP {status_code}")\n    if redirect_location:\n        current_parts.append(f"redirects to {redirect_location}")\n    if target_canonical:\n        current_parts.append(f"target canonical: {target_canonical}")\n    finding = create_finding(\n        rule=rule,\n        category="canonical",\n        priority=priority,\n        title=title,\n        page_url=page.get("path") or "/",\n        current_value=" — ".join(part for part in current_parts if part),\n        explanation=explanation,\n        recommendation=recommendation,\n        difficulty="developer",\n        source_pages=page.get("source_pages", []),\n        link_text_samples=page.get("link_text_samples", []),\n    )\n    finding.update({\n        "canonical_target_url": target,\n        "canonical_target_state": state,\n        "canonical_target_status_code": status_code,\n        "canonical_target_redirect_location": redirect_location,\n        "canonical_target_declared_canonical": target_canonical,\n        "canonical_target_evidence_source": page.get("canonical_target_evidence_source"),\n        "evidence_status": "needs_verification" if state == "cross_domain_needs_verification" else "confirmed",\n        "verification_state": "needs_verification" if state == "cross_domain_needs_verification" else "verified",\n        "limitation_code": "cross_domain_canonical_requires_confirmation" if state == "cross_domain_needs_verification" else "",\n        "confidence_score": 70 if state == "cross_domain_needs_verification" else 94,\n    })\n    return finding\n'''

marker = "\n\ndef sitemap_indexability_conflict(page: dict) -> bool:\n"
if marker not in scanner:
    raise SystemExit("Could not find sitemap conflict helper marker")
scanner = scanner.replace(marker, helper + marker, 1)
SCANNER.write_text(scanner)
