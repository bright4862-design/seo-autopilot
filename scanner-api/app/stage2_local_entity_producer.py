from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .stage2_coverage_evidence import (
    LOCAL_ENTITY_VERSION,
    NAP_CONSISTENCY_VERSION,
    assess_local_entity_completeness,
    assess_nap_consistency,
)


LOCAL_ENTITY_PRODUCER_VERSION = "local_entity_producer_v1_jsonld_explicit_identity"
LOCAL_CONTEXT_PROVENANCE_VERSION = "local_entity_context_provenance_v1"
MAX_JSONLD_SCRIPTS = 20
MAX_JSONLD_CHARS = 250_000
MAX_PAGE_ENTITY_OBSERVATIONS = 10
MAX_SCAN_ENTITY_OBSERVATIONS = 20
MAX_SURFACE_SCAN_NODES = 200

_LOCAL_TYPES = {
    "localbusiness",
    "store",
    "restaurant",
    "foodestablishment",
    "financialservice",
    "realestateagent",
    "professionalservice",
    "medicalbusiness",
    "automotivebusiness",
    "lodgingbusiness",
    "homeandconstructionbusiness",
    "healthandbeautybusiness",
    "sportsactivitylocation",
}

_EXPLICIT_ENTITY_ATTRS = ("data-entity-id", "data-location-id", "data-store-id")
_EXPLICIT_ENTITY_FIELD_NAMES = {
    "entity_id",
    "entityid",
    "location_id",
    "locationid",
    "store_id",
    "storeid",
}
_STATUS_FIELDS = ("businessStatus", "openingStatus", "status")
_STATUS_ALIASES = {
    "coming_soon": "coming_soon",
    "opening_soon": "coming_soon",
    "preopening": "coming_soon",
    "pre_opening": "coming_soon",
    "now_open": "open",
    "open": "open",
    "active": "open",
    "operating": "open",
    "closed": "closed",
    "temporarily_closed": "closed",
    "permanently_closed": "closed",
    "inactive": "closed",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _types(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in values:
        cleaned = _text(item)
        if cleaned:
            out.append(cleaned.rsplit("/", 1)[-1])
    return list(dict.fromkeys(out))[:12]


def _is_local_entity(node: dict[str, Any]) -> bool:
    lowered = {item.casefold() for item in _types(node.get("@type"))}
    return bool(lowered & _LOCAL_TYPES or any(item.endswith("business") for item in lowered))


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _walk(item)
        for key, item in value.items():
            if key == "@graph":
                continue
            if isinstance(item, (dict, list)):
                yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _address(value: Any) -> str:
    if isinstance(value, str):
        return _text(value)[:500]
    if not isinstance(value, dict):
        return ""
    country = value.get("addressCountry")
    if isinstance(country, dict):
        country = country.get("name") or country.get("@id")
    parts = [
        value.get("streetAddress"),
        value.get("addressLocality"),
        value.get("addressRegion"),
        value.get("postalCode"),
        country,
    ]
    return ", ".join(_text(part) for part in parts if _text(part))[:500]


def _hours(node: dict[str, Any]) -> str:
    direct = node.get("openingHours")
    values = direct if isinstance(direct, list) else ([direct] if direct else [])
    cleaned = [_text(item) for item in values if _text(item)]
    if cleaned:
        return " | ".join(cleaned)[:800]

    specs = node.get("openingHoursSpecification")
    specs = specs if isinstance(specs, list) else ([specs] if isinstance(specs, dict) else [])
    rows: list[str] = []
    for spec in specs[:14]:
        if not isinstance(spec, dict):
            continue
        days = spec.get("dayOfWeek")
        days = days if isinstance(days, list) else ([days] if days else [])
        day_text = ",".join(_text(day).rsplit("/", 1)[-1] for day in days if _text(day))
        opens = _text(spec.get("opens"))
        closes = _text(spec.get("closes"))
        row = " ".join(part for part in [day_text, f"{opens}-{closes}" if opens or closes else ""] if part)
        if row:
            rows.append(row)
    return " | ".join(rows)[:800]


def _parent(node: dict[str, Any]) -> str:
    value = node.get("parentOrganization") or node.get("branchOf")
    if isinstance(value, dict):
        return _text(value.get("@id") or value.get("name"))[:300]
    return _text(value)[:300]


def _entity_identity(value: Any) -> tuple[str, str, str]:
    """Return observed JSON-LD ID plus conservative cross-page match state.

    A fragment or relative ``@id`` is meaningful only after resolution against
    that document's base URL. This producer does not receive that trusted base,
    so relative IDs remain observed but unverified rather than being compared
    across pages as if ``#store`` meant the same branch everywhere.
    """
    entity_key = _text(value)[:500]
    if not entity_key:
        return "", "unverified", "jsonld_id_missing"
    parsed = urlparse(entity_key)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return entity_key, "verified", "absolute_http_jsonld_id"
    return entity_key, "unverified", "relative_jsonld_id_requires_base_resolution"


def _status_token(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    raw = raw.rsplit("/", 1)[-1]
    raw = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw)
    return re.sub(r"[^a-z0-9]+", "_", raw.casefold()).strip("_")


def _contextual_status(node: dict[str, Any], soup: BeautifulSoup) -> tuple[str | None, str, list[dict[str, str]]]:
    """Return only explicit machine status or conservative accepted-heading context."""
    for field in _STATUS_FIELDS:
        raw = _text(node.get(field))
        canonical = _STATUS_ALIASES.get(_status_token(raw))
        if canonical:
            return canonical, "observed_explicit", [{
                "source": "structured_data",
                "field": field,
                "value": raw[:160],
            }]

    heading_candidates: list[tuple[str, str]] = []
    title = soup.title
    if title is not None:
        heading_candidates.append(("title", _text(title.get_text(" "))[:160]))
    h1 = soup.find("h1")
    if h1 is not None:
        heading_candidates.append(("h1", _text(h1.get_text(" "))[:160]))

    for field, text in heading_candidates:
        lowered = text.casefold()
        canonical = None
        if re.search(r"\b(?:coming|opening)\s+soon\b", lowered):
            canonical = "coming_soon"
        elif re.search(r"\bnow\s+open\b", lowered):
            canonical = "open"
        elif re.search(r"\b(?:temporarily|permanently)\s+closed\b", lowered):
            canonical = "closed"
        elif re.fullmatch(r"closed", lowered.strip()):
            canonical = "closed"
        if canonical:
            return canonical, "observed_context", [{
                "source": "accepted_heading",
                "field": field,
                "value": text,
            }]

    return None, "not_verified", []


def _explicit_entity_reference(node: Any, entity_key: str) -> bool:
    if not entity_key or node is None:
        return False
    for attr in _EXPLICIT_ENTITY_ATTRS:
        if _text(getattr(node, "attrs", {}).get(attr)) == entity_key:
            return True
    name = re.sub(r"[^a-z0-9]+", "_", _text(getattr(node, "attrs", {}).get("name")).casefold()).strip("_")
    value = _text(getattr(node, "attrs", {}).get("value"))
    return name in _EXPLICIT_ENTITY_FIELD_NAMES and value == entity_key


def _subtree_has_explicit_entity_reference(node: Any, entity_key: str) -> bool:
    if _explicit_entity_reference(node, entity_key):
        return True
    count = 0
    for child in node.find_all(True):
        count += 1
        if count > MAX_SURFACE_SCAN_NODES:
            break
        if _explicit_entity_reference(child, entity_key):
            return True
    return False


def _is_store_finder_marker(node: Any) -> bool:
    attrs = getattr(node, "attrs", {})
    if "data-store-finder" in attrs or "data-store-locator" in attrs:
        return True
    node_id = re.sub(r"[^a-z0-9]+", "-", _text(attrs.get("id")).casefold()).strip("-")
    return node_id in {"store-finder", "store-locator", "location-finder", "location-locator"}


def _surface_provenance(
    soup: BeautifulSoup,
    *,
    entity_key: str,
    entity_match: str,
    discovery: dict[str, Any] | None,
) -> list[str]:
    """Record explicit HTML-surface provenance without using it to prove identity."""
    provenance = ["structured_data"]
    discovered_from = {
        _text(value)
        for value in ((discovery or {}).get("discovered_from") or [])
        if _text(value)
    }
    if "sitemap" in discovered_from:
        provenance.append("sitemap_reference")

    if entity_match != "verified" or not entity_key:
        return provenance

    for form in soup.find_all("form")[:20]:
        if _subtree_has_explicit_entity_reference(form, entity_key):
            provenance.append("form_explicit_entity_id")
            break

    scanned = 0
    for node in soup.find_all(True):
        scanned += 1
        if scanned > MAX_SURFACE_SCAN_NODES:
            break
        if not _is_store_finder_marker(node):
            continue
        if _subtree_has_explicit_entity_reference(node, entity_key):
            provenance.append("store_finder_explicit_entity_id")
            break

    return list(dict.fromkeys(provenance))


def extract_local_entity_observations(
    soup: BeautifulSoup,
    *,
    discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract bounded B13 structured observations from accepted HTML only.

    Cross-page identity is verified only from an absolute HTTP(S) JSON-LD
    ``@id``. Relative IDs are retained as observations but cannot establish a
    B14 entity match without trusted base-URL resolution. Name, address, phone,
    page family, form context and sitemap discovery never establish identity.
    """
    candidates: list[dict[str, Any]] = []
    malformed = 0
    scripts_seen = 0
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        if scripts_seen >= MAX_JSONLD_SCRIPTS:
            break
        scripts_seen += 1
        raw = str(script.string or script.get_text(" ") or "").strip()
        if not raw:
            continue
        if len(raw) > MAX_JSONLD_CHARS:
            malformed += 1
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            malformed += 1
            continue
        for node in _walk(data):
            if _is_local_entity(node):
                candidates.append(node)

    observations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    unique_candidate_count = 0
    for node in candidates:
        entity_key, entity_match, entity_identity_reason = _entity_identity(node.get("@id"))
        name = _text(node.get("name"))[:300]
        address = _address(node.get("address"))
        phone = _text(node.get("telephone"))[:120]
        regular_hours = _hours(node)
        contextual_status, contextual_status_state, contextual_status_provenance = _contextual_status(node, soup)
        dedupe_key = (entity_key, name, address, phone)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique_candidate_count += 1
        if len(observations) >= MAX_PAGE_ENTITY_OBSERVATIONS:
            continue
        if regular_hours:
            regular_hours_applicable: bool | None = True
        elif contextual_status in {"coming_soon", "closed"}:
            regular_hours_applicable = False
        elif contextual_status == "open":
            regular_hours_applicable = True
        else:
            regular_hours_applicable = None
        observations.append({
            "producer_version": LOCAL_ENTITY_PRODUCER_VERSION,
            "context_provenance_version": LOCAL_CONTEXT_PROVENANCE_VERSION,
            "applicable": True,
            "accepted": True,
            "source": "structured_data",
            "surface_provenance": _surface_provenance(
                soup,
                entity_key=entity_key,
                entity_match=entity_match,
                discovery=discovery,
            ),
            "schema_types": _types(node.get("@type")),
            "entity_key": entity_key,
            "entity_match": entity_match,
            "entity_identity_reason": entity_identity_reason,
            "name": name,
            "address": address,
            "phone": phone,
            "regular_hours": regular_hours,
            "regular_hours_applicable": regular_hours_applicable,
            "contextual_status": contextual_status,
            "contextual_status_state": contextual_status_state,
            "contextual_status_provenance": contextual_status_provenance,
            "holiday_hours": bool(node.get("specialOpeningHoursSpecification")),
            "photos": bool(node.get("image") or node.get("photo")),
            "same_as": bool(node.get("sameAs")),
            "parent_entity": _parent(node),
        })

    if observations:
        state, reason = "observed", "accepted_local_entity_structured_data"
    elif malformed:
        state, reason = "not_verified", "local_entity_structured_data_malformed"
    else:
        state, reason = "not_applicable", "no_local_entity_structured_data"
    return {
        "version": LOCAL_ENTITY_PRODUCER_VERSION,
        "context_provenance_version": LOCAL_CONTEXT_PROVENANCE_VERSION,
        "state": state,
        "reason": reason,
        "candidate_count": unique_candidate_count,
        "selected_count": len(observations),
        "selection_truncated": unique_candidate_count > len(observations),
        "malformed_script_count": malformed,
        "observations": observations,
    }


def _cross_page_nap_consistency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate B14 only where one verified entity ID spans multiple pages."""
    verified = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("accepted") is True
        and _text(row.get("entity_key"))
        and row.get("entity_match") == "verified"
    ]
    ambiguous = sum(
        1
        for row in rows
        if isinstance(row, dict) and row.get("entity_match") in {"ambiguous", "unverified"}
    )

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in verified:
        groups[_text(row.get("entity_key"))].append(row)

    comparable_keys: set[str] = set()
    comparable_rows: list[dict[str, Any]] = []
    for entity_key, members in groups.items():
        page_urls = {
            _text(member.get("page_url"))
            for member in members
            if _text(member.get("page_url"))
        }
        if len(page_urls) < 2:
            continue
        comparable_keys.add(entity_key)
        comparable_rows.extend(members)

    evaluated = assess_nap_consistency(comparable_rows)
    state = (evaluated.get("state") or "not_verified") if comparable_keys else "not_verified"

    return {
        **evaluated,
        "version": NAP_CONSISTENCY_VERSION,
        "state": state,
        "verified_observations": len(verified),
        "ambiguous_observations": ambiguous,
        "comparable_entity_groups": len(comparable_keys),
        "unverified_entity_groups": max(0, len(groups) - len(comparable_keys)),
        "scope": "cross_page_explicit_entity_identity",
        "sitewide_consistency_claim": False,
    }


def build_local_entity_scan_evidence(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Build bounded B13/B14 summaries from producer observations on retained pages."""
    rows: list[dict[str, Any]] = []
    eligible = 0
    for page in pages:
        envelope = page.get("local_entity_observations")
        if not isinstance(envelope, dict) or envelope.get("version") != LOCAL_ENTITY_PRODUCER_VERSION:
            continue
        observations = envelope.get("observations")
        if not isinstance(observations, list):
            continue
        page_discovery = {
            _text(value)
            for value in (page.get("discovered_from") or [])
            if _text(value)
        }
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            eligible += 1
            if len(rows) >= MAX_SCAN_ENTITY_OBSERVATIONS:
                continue
            row = dict(observation)
            row["page_url"] = _text(page.get("final_url") or page.get("url"))
            row["source"] = _text(observation.get("source")) or "structured_data"
            surface_provenance = [
                _text(value)
                for value in (observation.get("surface_provenance") or [])
                if _text(value)
            ]
            if "sitemap" in page_discovery:
                surface_provenance.append("sitemap_reference")
            row["surface_provenance"] = list(dict.fromkeys(surface_provenance))
            rows.append(row)

    completeness = []
    for row in rows:
        result = assess_local_entity_completeness(row)
        completeness.append({
            "page_url": row.get("page_url") or "",
            "entity_key": row.get("entity_key") or "",
            "entity_match": row.get("entity_match") or "unverified",
            "entity_identity_reason": row.get("entity_identity_reason") or "",
            "source": row.get("source") or "structured_data",
            "surface_provenance": list(row.get("surface_provenance") or []),
            "context_provenance_version": row.get("context_provenance_version") or "",
            "contextual_status_state": row.get("contextual_status_state") or "not_verified",
            "contextual_status_provenance": list(row.get("contextual_status_provenance") or []),
            **result,
        })
    nap = _cross_page_nap_consistency(rows)
    return {
        "producer_version": LOCAL_ENTITY_PRODUCER_VERSION,
        "context_provenance_version": LOCAL_CONTEXT_PROVENANCE_VERSION,
        "local_entity_version": LOCAL_ENTITY_VERSION,
        "nap_consistency_version": NAP_CONSISTENCY_VERSION,
        "eligible_observations": eligible,
        "selected_observations": len(rows),
        "selection_truncated": eligible > len(rows),
        "completeness": completeness,
        "nap_consistency": nap,
    }
