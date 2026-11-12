"""Pure named-crawler robots evidence for GEO readiness.

This adapter performs no fetching and never impersonates third-party crawlers. It
only normalizes exact per-user-agent decisions already retained by the scanner.
Blocking a training crawler is neutral structural evidence, not a GEO defect.
"""
from __future__ import annotations

from hashlib import sha256
from types import MappingProxyType

VERSION = "geo_named_robots_evidence_v1"

NAMED_CRAWLERS = MappingProxyType({
    "oai_searchbot": MappingProxyType({
        "user_agent": "OAI-SearchBot",
        "purpose": "search",
        "field": "robots_txt_oai_searchbot_allowed",
    }),
    "gptbot": MappingProxyType({
        "user_agent": "GPTBot",
        "purpose": "training",
        "field": "robots_txt_gptbot_allowed",
    }),
    "googlebot": MappingProxyType({
        "user_agent": "Googlebot",
        "purpose": "search",
        "field": "robots_txt_googlebot_allowed",
    }),
})

_ROBOTS_STATUSES = frozenset({"available", "missing", "unavailable", "access_limited"})


def _page_ref(page: dict) -> str:
    value = page.get("page_id") or page.get("url")
    if not isinstance(value, str) or not value.strip() or len(value) > 8192:
        raise ValueError("Expected bounded page_id or URL")
    return "p_" + sha256(value.encode()).hexdigest()[:24]


def _evidence_ref(page_ref: str, crawler_id: str, allowed: bool, status: str) -> str:
    material = f"{page_ref}\n{crawler_id}\n{int(allowed)}\n{status}".encode()
    digest = sha256(material).hexdigest()[:24]
    return f"{VERSION}:{page_ref}:{crawler_id}:{digest}"


def extract_named_robots_evidence(page: dict) -> dict:
    """Normalize already-retained robots decisions for a fixed crawler registry.

    `observed` means only that FixList retained a deterministic robots.txt
    decision for that exact user-agent token. It is not proof that the provider
    fetched, indexed, cited, ranked, included, displayed, or sent traffic.
    """
    if not isinstance(page, dict):
        raise ValueError("Expected page object")
    page_ref = _page_ref(page)

    rules_known = page.get("robots_txt_rules_known")
    if rules_known is not None and type(rules_known) is not bool:
        raise ValueError("Malformed robots rules-known state")

    status = page.get("robots_txt_status")
    if status is not None and (not isinstance(status, str) or status not in _ROBOTS_STATUSES):
        raise ValueError("Malformed robots status")
    status_label = status or "unknown"

    status_code = page.get("robots_txt_status_code")
    if status_code is not None and (type(status_code) is not int or not 0 <= status_code <= 599):
        raise ValueError("Malformed robots status code")

    if status in {"available", "missing"} and rules_known is False:
        raise ValueError("Known robots status contradicts rules-known state")
    if status in {"unavailable", "access_limited"} and rules_known is True:
        raise ValueError("Unavailable robots status contradicts rules-known state")

    values = {}
    for crawler_id, spec in NAMED_CRAWLERS.items():
        value = page.get(spec["field"])
        if value is not None and type(value) is not bool:
            raise ValueError(f"Malformed {spec['user_agent']} robots directive")
        if value is not None and rules_known is not True:
            raise ValueError(f"Unverified {spec['user_agent']} robots directive")
        values[crawler_id] = value

    bots = []
    for crawler_id, spec in NAMED_CRAWLERS.items():
        allowed = values[crawler_id]
        if rules_known is True and type(allowed) is bool:
            bots.append({
                "crawler_id": crawler_id,
                "user_agent": spec["user_agent"],
                "purpose": spec["purpose"],
                "state": "observed",
                "directive": "allow" if allowed else "disallow",
                "evidence_ref": _evidence_ref(page_ref, crawler_id, allowed, status_label),
                "reason": "Retained robots.txt evaluation for this exact user-agent; not proof of provider access or visibility",
            })
        else:
            bots.append({
                "crawler_id": crawler_id,
                "user_agent": spec["user_agent"],
                "purpose": spec["purpose"],
                "state": "not_verified",
                "directive": None,
                "evidence_ref": "",
                "reason": (
                    "Robots rules were not retained as known"
                    if rules_known is not True
                    else "No retained directive evaluation for this exact user-agent"
                ),
            })

    return {
        "version": VERSION,
        "page_id": page_ref,
        "robots_status": status_label,
        "rules_known": rules_known is True,
        "bots": bots,
        "claim_boundary": "robots_policy_only_not_provider_fetch_indexing_citations_ranking_visibility_or_traffic",
    }
