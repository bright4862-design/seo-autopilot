from __future__ import annotations

from collections import Counter
from urllib.parse import urldefrag, urljoin, urlparse

from .page_evidence_gate import page_has_usable_html
from .robots_policy import SCANNER_USER_AGENT, SEARCH_USER_AGENT
from .security import REDIRECT_STATUSES, is_public_http_url, safe_get_once


REDIRECT_EVIDENCE_VERSION = "redirect_evidence_v4_specific_top_level_home_catchall"
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


def _comparable_origin_key(value: str) -> tuple[str, int | None]:
    parsed = urlparse(str(value or ""))
    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host, parsed.port


def _identity_path_query(value: str) -> tuple[str, str]:
    parsed = urlparse(str(value or ""))
    path = (parsed.path or "/").rstrip("/") or "/"
    return path, parsed.query or ""


def _is_origin_alias_identity_redirect(evidence: dict) -> bool:
    """True only for one-hop apex/www aliases preserving scheme, path and query."""
    if str(evidence.get("state") or "") != "single_redirect":
        return False
    if int(evidence.get("hop_count") or 0) != 1:
        return False
    source = str(evidence.get("source_url") or "")
    destination = str(evidence.get("destination_url") or "")
    source_parsed = urlparse(source)
    destination_parsed = urlparse(destination)
    if not source_parsed.hostname or not destination_parsed.hostname:
        return False
    if source_parsed.scheme != destination_parsed.scheme:
        return False
    if _comparable_origin_key(source) != _comparable_origin_key(destination):
        return False
    if (source_parsed.hostname or "").lower() == (destination_parsed.hostname or "").lower():
        return False
    return _identity_path_query(source) == _identity_path_query(destination)


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
    max_decoded_bytes: int | None = None,
):
    source = _normalize_url(url)
    evidence = _base_evidence(source or str(url or ""))
    if not source:
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
            response = await safe_get_once(
                client,
                current,
                max_decoded_bytes=max_decoded_bytes,
            )
            if response is None:
                evidence.update({
                    "state": "blocked_non_public_redirect",
                    "hop_count": len(hops),
                    "hops": hops,
                    "chain": chain,
                    "destination_url": current,
                    "fetch_error": "blocked_non_public_redirect" if hops else "blocked_non_public_host",
                })
                return None, evidence
        except Exception as exc:
            # A transport/decode exception is scanner access evidence, not proof
            # of a final HTTP status. Preserve it separately so the report can
            # say the destination was not verified without inventing a 404.
            evidence.update({
                "state": "redirect_destination_unverified" if hops else "fetch_failed",
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


def _absolute_canonical(page: dict, destination_url: str) -> str:
    canonical = str(page.get("canonical_url") or page.get("canonical") or "").strip()
    if not canonical:
        return ""
    return _normalize_url(urljoin(destination_url or str(page.get("final_url") or ""), canonical))


def _noindex(page: dict) -> bool:
    if str(page.get("indexability_state") or "") == "Noindexed":
        return True
    directives = page.get("effective_search_robots_directives") or []
    return "noindex" in {str(value or "").strip().lower() for value in directives}


def _body_bytes(page: dict) -> int:
    explicit = page.get("response_body_bytes")
    try:
        if explicit is not None:
            return max(0, int(explicit))
    except (TypeError, ValueError):
        pass
    html = page.get("_html") or page.get("html") or page.get("raw_html")
    if isinstance(html, str):
        return len(html.encode("utf-8"))
    try:
        return max(0, int(page.get("html_size") or 0))
    except (TypeError, ValueError):
        return 0


def _html_parse_ok(page: dict) -> bool:
    status = int(page.get("status_code") or 0)
    if not 200 <= status < 300 or str(page.get("fetch_error") or "").strip():
        return False
    content_type = str(page.get("content_type") or "").lower()
    if content_type and "html" not in content_type:
        return False
    return page_has_usable_html(page)


def _same_url_except_trailing_slash(source_url: str, destination_url: str) -> bool:
    source = _normalize_url(source_url)
    destination = _normalize_url(destination_url)
    if not source or not destination:
        return False
    source_parsed = urlparse(source)
    destination_parsed = urlparse(destination)
    return (
        _comparable_origin_key(source) == _comparable_origin_key(destination)
        and source_parsed.query == destination_parsed.query
        and ((source_parsed.path or "/").rstrip("/") or "/")
        == ((destination_parsed.path or "/").rstrip("/") or "/")
    )


def _looks_like_wrong_destination(source_url: str, destination_url: str) -> bool:
    """Detect strong generic catch-all redirects without site-specific slugs.

    A specific URL collapsing to the same site's homepage is materially different
    from slash/case/canonical normalization: HTTP 200 proves availability, not
    relevance. Multi-segment paths are always specific here; a top-level route is
    specific only when its slug contains multiple lexical tokens. This keeps
    conventional aliases such as /home out of the wrong-destination bucket.
    """
    source = _normalize_url(source_url)
    destination = _normalize_url(destination_url)
    if not source or not destination or _same_url_except_trailing_slash(source, destination):
        return False
    if _comparable_origin_key(source) != _comparable_origin_key(destination):
        return False
    source_path = (urlparse(source).path or "/").rstrip("/") or "/"
    destination_path = (urlparse(destination).path or "/").rstrip("/") or "/"
    source_segments = [segment for segment in source_path.split("/") if segment]
    if destination_path != "/" or not source_segments:
        return False
    if len(source_segments) >= 2:
        return True
    top_level = source_segments[0].lower().replace("_", "-")
    if top_level in {"home", "homepage", "index", "index.html", "index.htm"}:
        return False
    return len([token for token in top_level.split("-") if token]) >= 2


def _redirect_outcome(page: dict, evidence: dict, destination_state: str) -> str:
    if int(evidence.get("hop_count") or 0) <= 0 and str(evidence.get("state") or "") == "not_redirected":
        return ""

    state = str(evidence.get("state") or "")
    status = int(evidence.get("destination_status_code") or page.get("status_code") or 0)
    if state == "redirect_destination_unverified":
        return "redirect_destination_unverified"
    if state in {
        "redirect_destination_blocked_by_robots",
        "redirect_loop",
        "redirect_missing_location",
        "redirect_invalid_location",
        "redirect_chain_limit_exceeded",
        "blocked_non_public_redirect",
    }:
        return "redirect_destination_unusable"
    if status >= 400:
        return "redirect_destination_unusable"

    destination_url = str(evidence.get("destination_url") or page.get("final_url") or "")
    canonical = _absolute_canonical(page, destination_url)
    canonical_elsewhere = bool(canonical and _normalize_url(destination_url) and canonical != _normalize_url(destination_url))
    content_type = str(page.get("content_type") or "").lower()
    unsuitable_content = bool(status and 200 <= status < 300 and content_type and "html" not in content_type)
    if (
        destination_state in {"Noindexed", "Canonicalized"}
        or _noindex(page)
        or canonical_elsewhere
        or unsuitable_content
    ):
        return "redirect_to_nonindexable_page"
    if 200 <= status < 300 and _html_parse_ok(page):
        source_url = str(evidence.get("source_url") or page.get("url") or "")
        if _looks_like_wrong_destination(source_url, destination_url):
            return "redirect_to_wrong_destination"
        return "redirect_to_usable_page"
    if 200 <= status < 300:
        return "redirect_destination_unusable"
    return "redirect_destination_unusable"


def _fetch_evidence(page: dict, evidence: dict, destination_state: str, classification: str) -> dict:
    destination_url = str(evidence.get("destination_url") or page.get("final_url") or "")
    fetch_error = str(evidence.get("fetch_error") or page.get("fetch_error") or "").strip()
    robots_status = destination_state or str(page.get("robots_indexability_status") or "")
    return {
        "requested_url": str(evidence.get("source_url") or page.get("url") or ""),
        "redirect_chain": [
            {
                "url": str(hop.get("url") or ""),
                "status": int(hop.get("status_code") or 0),
                "location": str(hop.get("location") or ""),
            }
            for hop in (evidence.get("hops") or [])
            if isinstance(hop, dict)
        ],
        "final_url": destination_url,
        "final_status": int(evidence.get("destination_status_code") or page.get("status_code") or 0),
        "final_content_type": str(page.get("content_type") or ""),
        "body_bytes": _body_bytes(page),
        "html_parse_ok": _html_parse_ok(page),
        "fetch_error": fetch_error or None,
        "robots_status": robots_status,
        "canonical_url": _absolute_canonical(page, destination_url),
        "noindex": _noindex(page),
        "classification": classification,
    }


def apply_redirect_evidence(page: dict, evidence: dict) -> dict:
    raw_state = str(evidence.get("state") or "not_redirected")
    raw_hop_count = int(evidence.get("hop_count") or 0)
    origin_alias_redirect = _is_origin_alias_identity_redirect(evidence)
    state = "not_redirected" if origin_alias_redirect else raw_state
    hop_count = 0 if origin_alias_redirect else raw_hop_count
    redirected = hop_count > 0 or state in {
        "redirect_loop",
        "redirect_missing_location",
        "redirect_invalid_location",
        "redirect_chain_limit_exceeded",
        "redirect_destination_blocked_by_robots",
        "redirect_destination_unverified",
        "blocked_non_public_redirect",
    }

    destination_state = str(page.get("indexability_state") or "Unknown because of access or rendering limitations")
    destination_indexable = bool(page.get("indexable") is True)
    if evidence.get("destination_googlebot_blocked") is True:
        destination_state = "Blocked by robots.txt"
        destination_indexable = False
    elif raw_state == "redirect_destination_blocked_by_robots":
        destination_state = "Blocked by robots.txt"
        destination_indexable = False
    elif raw_state in {
        "redirect_loop",
        "redirect_missing_location",
        "redirect_invalid_location",
        "redirect_chain_limit_exceeded",
        "redirect_destination_unverified",
        "blocked_non_public_redirect",
    }:
        destination_state = "Unknown because of access or rendering limitations"
        destination_indexable = False

    outcome = _redirect_outcome(page, evidence, destination_state)
    fetch_evidence = _fetch_evidence(page, evidence, destination_state, outcome)

    page.update({
        "redirect_evidence_version": REDIRECT_EVIDENCE_VERSION,
        "redirect_state": state,
        "redirect_outcome": outcome,
        "redirect_fetch_evidence": fetch_evidence,
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
        "origin_alias_redirect": origin_alias_redirect,
        "origin_alias_redirect_hop_count": raw_hop_count if origin_alias_redirect else 0,
        "origin_alias_redirect_chain": list(evidence.get("chain") or []) if origin_alias_redirect else [],
        "origin_alias_destination_url": str(evidence.get("destination_url") or "") if origin_alias_redirect else "",
        "origin_alias_destination_indexability_state": destination_state if origin_alias_redirect else "",
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
    origin_aliases = [page for page in pages if page.get("origin_alias_redirect") is True]
    states = Counter(str(page.get("redirect_state") or "unknown") for page in redirected)
    outcomes = Counter(str(page.get("redirect_outcome") or "unknown") for page in redirected)
    sitemap_redirects = sum(1 for page in redirected if "sitemap" in set(page.get("discovered_from") or []))
    internal_link_redirects = sum(1 for page in redirected if "internal_link" in set(page.get("discovered_from") or []))
    alias_total = 0
    sample_aliases: list[dict] = []

    for page in pages:
        aliases = [item for item in (page.get("redirect_aliases") or []) if isinstance(item, dict)]
        sample_aliases.extend(aliases)
        recorded_total = page.get("redirect_alias_total")
        try:
            alias_total += max(0, int(recorded_total)) if recorded_total is not None else len(aliases)
        except (TypeError, ValueError):
            alias_total += len(aliases)

        recorded_states = page.get("redirect_alias_state_counts")
        if isinstance(recorded_states, dict):
            states.update({str(key): int(value or 0) for key, value in recorded_states.items()})
        else:
            states.update(str(item.get("redirect_state") or "unknown") for item in aliases)
        recorded_outcomes = page.get("redirect_alias_outcome_counts")
        if isinstance(recorded_outcomes, dict):
            outcomes.update({str(key): int(value or 0) for key, value in recorded_outcomes.items()})
        else:
            outcomes.update(str(item.get("redirect_outcome") or "unknown") for item in aliases)

        if page.get("redirect_alias_sitemap_total") is not None:
            sitemap_redirects += max(0, int(page.get("redirect_alias_sitemap_total") or 0))
        else:
            sitemap_redirects += sum(1 for item in aliases if "sitemap" in set(item.get("discovered_from") or []))
        if page.get("redirect_alias_internal_link_total") is not None:
            internal_link_redirects += max(0, int(page.get("redirect_alias_internal_link_total") or 0))
        else:
            internal_link_redirects += sum(1 for item in aliases if "internal_link" in set(item.get("discovered_from") or []))

    sample_records = [*redirected, *sample_aliases][:20]
    return {
        "version": REDIRECT_EVIDENCE_VERSION,
        "redirected_pages": len(redirected) + alias_total,
        "origin_alias_redirects": len(origin_aliases),
        "state_counts": dict(sorted(states.items())),
        "outcome_counts": dict(sorted(outcomes.items())),
        "sitemap_redirects": sitemap_redirects,
        "internal_link_redirects": internal_link_redirects,
        "redirects": [
            {
                "outcome": page.get("redirect_outcome"),
                **dict(page.get("redirect_fetch_evidence") or {}),
            }
            for page in sample_records
            if isinstance(page.get("redirect_fetch_evidence"), dict)
        ],
        "representative_redirects": [
            {
                "source": page.get("redirect_source_url") or page.get("url"),
                "destination": page.get("redirect_destination_url"),
                "state": page.get("redirect_state"),
                "outcome": page.get("redirect_outcome"),
                "hop_count": page.get("redirect_hop_count"),
                "final_status": (page.get("redirect_fetch_evidence") or {}).get("final_status"),
            }
            for page in sample_records
        ],
        "representative_origin_aliases": [
            {
                "source": page.get("redirect_source_url") or page.get("url"),
                "destination": page.get("origin_alias_destination_url") or page.get("final_url"),
                "hop_count": page.get("origin_alias_redirect_hop_count"),
            }
            for page in origin_aliases[:20]
        ],
    }
