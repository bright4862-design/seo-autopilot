from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .stage2_coverage_evidence import (
    LOCAL_ENTITY_VERSION,
    NAP_CONSISTENCY_VERSION,
    assess_local_entity_completeness,
    assess_nap_consistency,
)


LOCAL_ENTITY_PRODUCER_VERSION = "local_entity_producer_v1_jsonld_explicit_identity"
MAX_JSONLD_SCRIPTS = 20
MAX_JSONLD_CHARS = 250_000
MAX_PAGE_ENTITY_OBSERVATIONS = 10
MAX_SCAN_ENTITY_OBSERVATIONS = 20

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


def extract_local_entity_observations(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract bounded B13 structured observations from accepted HTML only.

    Cross-page identity is verified only from an explicit JSON-LD ``@id``.
    Name, address, and phone similarity never establish an entity match.
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
    for node in candidates:
        entity_key = _text(node.get("@id"))[:500]
        name = _text(node.get("name"))[:300]
        address = _address(node.get("address"))
        phone = _text(node.get("telephone"))[:120]
        regular_hours = _hours(node)
        dedupe_key = (entity_key, name, address, phone)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        observations.append({
            "producer_version": LOCAL_ENTITY_PRODUCER_VERSION,
            "applicable": True,
            "accepted": True,
            "source": "structured_data",
            "schema_types": _types(node.get("@type")),
            "entity_key": entity_key,
            "entity_match": "verified" if entity_key else "unverified",
            "name": name,
            "address": address,
            "phone": phone,
            "regular_hours": regular_hours,
            "regular_hours_applicable": True if regular_hours else None,
            "contextual_status": None,
            "holiday_hours": bool(node.get("specialOpeningHoursSpecification")),
            "photos": bool(node.get("image") or node.get("photo")),
            "same_as": bool(node.get("sameAs")),
            "parent_entity": _parent(node),
        })
        if len(observations) >= MAX_PAGE_ENTITY_OBSERVATIONS:
            break

    if observations:
        state, reason = "observed", "accepted_local_entity_structured_data"
    elif malformed:
        state, reason = "not_verified", "local_entity_structured_data_malformed"
    else:
        state, reason = "not_applicable", "no_local_entity_structured_data"
    return {
        "version": LOCAL_ENTITY_PRODUCER_VERSION,
        "state": state,
        "reason": reason,
        "candidate_count": len(candidates),
        "selected_count": len(observations),
        "selection_truncated": len(candidates) > len(observations),
        "malformed_script_count": malformed,
        "observations": observations,
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
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            eligible += 1
            if len(rows) >= MAX_SCAN_ENTITY_OBSERVATIONS:
                continue
            row = dict(observation)
            row["page_url"] = _text(page.get("final_url") or page.get("url"))
            row["source"] = "structured_data"
            rows.append(row)

    completeness = []
    for row in rows:
        result = assess_local_entity_completeness(row)
        completeness.append({
            "page_url": row.get("page_url") or "",
            "entity_key": row.get("entity_key") or "",
            "entity_match": row.get("entity_match") or "unverified",
            "source": row.get("source") or "structured_data",
            **result,
        })
    nap = assess_nap_consistency(rows)
    return {
        "producer_version": LOCAL_ENTITY_PRODUCER_VERSION,
        "local_entity_version": LOCAL_ENTITY_VERSION,
        "nap_consistency_version": NAP_CONSISTENCY_VERSION,
        "eligible_observations": eligible,
        "selected_observations": len(rows),
        "selection_truncated": eligible > len(rows),
        "completeness": completeness,
        "nap_consistency": nap,
    }
