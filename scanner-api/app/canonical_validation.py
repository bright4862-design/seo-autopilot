from __future__ import annotations

import asyncio
import time
from collections import Counter
from urllib.parse import urldefrag, urljoin, urlparse

from .extract import extract_page
from .robots_policy import SCANNER_USER_AGENT, SEARCH_USER_AGENT, annotate_robots_evidence
from .security import is_public_http_url


CANONICAL_TARGET_EVIDENCE_VERSION = "canonical_target_evidence_v2_origin_alias"
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


def _comparable_host(value: str) -> str:
    host = str(value or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def _is_transport_origin_alias(source: str, target: str) -> bool:
    """Return True only for a same-page, same-scheme apex/www identity alias."""
    source_url = _normalize_url(source)
    target_url = _normalize_url(target)
    if not source_url or not target_url:
        return False
    source_parsed = urlparse(source_url)
    target_parsed = urlparse(target_url)
    source_host = (source_parsed.hostname or "").lower()
    target_host = (target_parsed.hostname or "").lower()
    if not source_host or not target_host or source_host == target_host:
        return False
    return (
        source_parsed.scheme == target_parsed.scheme
        and source_parsed.port == target_parsed.port
        and _comparable_host(source_host) == _comparable_host(target_host)
        and (source_parsed.path or "/") == (target_parsed.path or "/")
        and source_parsed.query == target_parsed.query
    )


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
        if _is_transport_origin_alias(source_url, target):
            _apply_evidence(page, target, {
                "state": "origin_alias_equivalent",
                "target_url": target,
                "status_code": int(page.get("status_code") or 0),
                "indexability_state": str(page.get("indexability_state") or "Indexable"),
                "fetch_error": "",
                "location": "",
                "target_canonical": "",
                "evidence_source": "origin_alias_contract",
            })
            continue
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
        "origin_alias_equivalent_count": int(states.get("origin_alias_equivalent", 0)),
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
