from __future__ import annotations

from collections import Counter
from urllib.parse import urldefrag, urljoin, urlparse

from .robots_policy import SCANNER_USER_AGENT, SEARCH_USER_AGENT
from .security import REDIRECT_STATUSES, is_public_http_url


REDIRECT_EVIDENCE_VERSION = "redirect_evidence_v2_trailing_slash_identity"
DEFAULT_MAX_REDIRECTS = 5


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
    return parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        fragment="",
    ).geturl()


def _origin_key(value: str) -> tuple[str, int | None]:
    parsed = urlparse(str(value or ""))
    return ((parsed.hostname or "").lower(), parsed.port)


def _policy_applies(robots_policy, url: str) -> bool:
    policy_url = str(getattr(robots_policy, "url", "") or "")
    return bool(policy_url and _origin_key(policy_url) == _origin_key(url))


def _base_evidence(source_url: str) -> dict:
    return {
        "version": REDIRECT_EVIDENCE_VERSION,
        "state": "not_redirected",
        "source_url": source_url,
        "source_path": urlparse(source_url).path or "/",
        "hop_count": 0,
        "hops": [],
        "chain": [source_url] if source_url else [],
        "destination_url": source_url,
        "destination_status_code": 0,
        "destination_googlebot_blocked": False,
        "destination_scanner_blocked": False,
        "fetch_error": "",
        "truncated": False,
    }


async def fetch_with_redirect_evidence(
    client,
    url: str,
    robots_policy=None,
    *,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
):
    source = _normalize_url(url)
    evidence = _base_evidence(source or str(url or ""))
    if not source or not is_public_http_url(source):
        evidence.update({
            "state": "blocked_non_public_redirect",
            "fetch_error": "blocked_non_public_host",
            "destination_url": source or str(url or ""),
        })
        return None, evidence

    current = source
    visited = {source}
    chain = [source]
    hops: list[dict] = []

    for _ in range(max(0, int(max_redirects)) + 1):
        if not is_public_http_url(current):
            evidence.update({
                "state": "blocked_non_public_redirect",
                "hop_count": len(hops),
                "hops": hops,
                "chain": chain,
                "destination_url": current,
                "fetch_error": "blocked_non_public_redirect",
            })
            return None, evidence

        scanner_allowed = None
        googlebot_allowed = None
        if robots_policy is not None and _policy_applies(robots_policy, current):
            scanner_allowed = robots_policy.allowed(SCANNER_USER_AGENT, current)
            googlebot_allowed = robots_policy.allowed(SEARCH_USER_AGENT, current)
            if current != source and scanner_allowed is False:
                evidence.update({
                    "state": "redirect_destination_blocked_by_robots",
                    "hop_count": len(hops),
                    "hops": hops,
                    "chain": chain,
                    "destination_url": current,
                    "destination_googlebot_blocked": googlebot_allowed is False,
                    "destination_scanner_blocked": True,
                    "fetch_error": "redirect_destination_blocked_by_robots",
                })
                return None, evidence

        try:
            response = await client.get(current)
        except Exception as exc:
            evidence.update({
                "state": "redirect_destination_failed" if hops else "fetch_failed",
                "hop_count": len(hops),
                "hops": hops,
                "chain": chain,
                "destination_url": current,
                "destination_googlebot_blocked": googlebot_allowed is False,
                "destination_scanner_blocked": scanner_allowed is False,
                "fetch_error": str(exc)[:180],
            })
            return None, evidence

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code not in REDIRECT_STATUSES:
            evidence.update({
                "state": "redirect_chain" if len(hops) >= 2 else ("single_redirect" if hops else "not_redirected"),
                "hop_count": len(hops),
                "hops": hops,
                "chain": chain,
                "destination_url": current,
                "destination_status_code": status_code,
                "destination_googlebot_blocked": googlebot_allowed is False,
                "destination_scanner_blocked": scanner_allowed is False,
            })
            return response, evidence

        location = str(response.headers.get("location") or "").strip()
        if not location:
            hops.append({"url": current, "status_code": status_code, "location": ""})
            evidence.update({
                "state": "redirect_missing_location",
                "hop_count": len(hops),
                "hops": hops,
                "chain": chain,
                "destination_url": current,
                "destination_status_code": status_code,
                "fetch_error": "redirect_response_missing_location",
            })
            return response, evidence

        next_url = _normalize_url(urljoin(current, location))
        hops.append({"url": current, "status_code": status_code, "location": next_url})
        if not next_url:
            evidence.update({
                "state": "redirect_invalid_location",
                "hop_count": len(hops),
                "hops": hops,
                "chain": chain,
                "destination_url": location,
                "destination_status_code": status_code,
                "fetch_error": "redirect_location_invalid",
            })
            return response, evidence

        if next_url in visited:
            chain.append(next_url)
            evidence.update({
                "state": "redirect_loop",
                "hop_count": len(hops),
                "hops": hops,
                "chain": chain,
                "destination_url": next_url,
                "destination_status_code": status_code,
                "fetch_error": "redirect_loop",
            })
            return response, evidence

        visited.add(next_url)
        chain.append(next_url)
        current = next_url

    evidence.update({
        "state": "redirect_chain_limit_exceeded",
        "hop_count": len(hops),
        "hops": hops,
        "chain": chain,
        "destination_url": current,
        "fetch_error": "redirect_chain_limit_exceeded",
        "truncated": True,
    })
    return None, evidence


def apply_redirect_evidence(page: dict, evidence: dict) -> dict:
    state = str(evidence.get("state") or "not_redirected")
    hop_count = int(evidence.get("hop_count") or 0)
    redirected = hop_count > 0 or state in {
        "redirect_loop",
        "redirect_missing_location",
        "redirect_invalid_location",
        "redirect_chain_limit_exceeded",
        "redirect_destination_blocked_by_robots",
        "redirect_destination_failed",
        "blocked_non_public_redirect",
    }

    destination_state = str(page.get("indexability_state") or "Unknown because of access or rendering limitations")
    destination_indexable = bool(page.get("indexable") is True)
    if evidence.get("destination_googlebot_blocked") is True:
        destination_state = "Blocked by robots.txt"
        destination_indexable = False
    elif state == "redirect_destination_blocked_by_robots":
        destination_state = "Blocked by robots.txt"
        destination_indexable = False
    elif state in {
        "redirect_loop",
        "redirect_missing_location",
        "redirect_invalid_location",
        "redirect_chain_limit_exceeded",
        "blocked_non_public_redirect",
    }:
        destination_state = "Unknown because of access or rendering limitations"
        destination_indexable = False

    page.update({
        "redirect_evidence_version": REDIRECT_EVIDENCE_VERSION,
        "redirect_state": state,
        "redirect_source_url": str(evidence.get("source_url") or page.get("url") or ""),
        "redirect_source_path": str(evidence.get("source_path") or urlparse(str(page.get("url") or "")).path or "/"),
        "redirect_hop_count": hop_count,
        "redirect_hops": list(evidence.get("hops") or []),
        "redirect_chain": list(evidence.get("chain") or []),
        "redirect_destination_url": str(evidence.get("destination_url") or page.get("final_url") or ""),
        "redirect_destination_status_code": int(evidence.get("destination_status_code") or page.get("status_code") or 0),
        "redirect_destination_indexability_state": destination_state if redirected else "",
        "redirect_destination_indexable": destination_indexable if redirected else None,
        "redirect_destination_googlebot_blocked": evidence.get("destination_googlebot_blocked") is True,
        "redirect_destination_scanner_blocked": evidence.get("destination_scanner_blocked") is True,
        "redirect_fetch_error": str(evidence.get("fetch_error") or ""),
        "redirect_chain_truncated": evidence.get("truncated") is True,
    })
    if redirected:
        page["indexable"] = False
        page["indexability_state"] = "Redirected"
        page["robots_indexability_status"] = "redirected"
    return page


def summarize_redirect_evidence(pages: list[dict]) -> dict:
    redirected = [
        page for page in pages
        if int(page.get("redirect_hop_count") or 0) > 0
        or str(page.get("redirect_state") or "") not in {"", "not_redirected"}
    ]
    states = Counter(str(page.get("redirect_state") or "unknown") for page in redirected)
    return {
        "version": REDIRECT_EVIDENCE_VERSION,
        "redirected_pages": len(redirected),
        "state_counts": dict(sorted(states.items())),
        "sitemap_redirects": sum(
            1 for page in redirected if "sitemap" in set(page.get("discovered_from") or [])
        ),
        "internal_link_redirects": sum(
            1 for page in redirected if "internal_link" in set(page.get("discovered_from") or [])
        ),
        "representative_redirects": [
            {
                "source": page.get("redirect_source_url") or page.get("url"),
                "destination": page.get("redirect_destination_url"),
                "state": page.get("redirect_state"),
                "hop_count": page.get("redirect_hop_count"),
            }
            for page in redirected[:20]
        ],
    }
