"""Pure NextGen browser/performance evidence helpers.

No function in this module performs network I/O. Provider/browser responses are
normalized after observation. Field and lab evidence remain separate.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

PERFORMANCE_EVIDENCE_VERSION = "nextgen_performance_evidence_v1"
FIELD_PERFORMANCE_VERSION = "nextgen_field_performance_v1"
LIGHTHOUSE_EVIDENCE_VERSION = "nextgen_lighthouse_evidence_v1"
REPRESENTATIVE_SAMPLE_VERSION = "nextgen_performance_sample_v1"
CRITICAL_PARITY_VERSION = "nextgen_critical_content_parity_v1"
MAX_PERFORMANCE_SAMPLE_PAGES = 12

PROVIDER_STATES = {"connected", "disconnected", "unavailable", "rate_limited", "provider_error"}
FIELD_METRICS = {
    "lcp": ("ms", ("lcp", "lcp_ms", "largest_contentful_paint", "largest_contentful_paint_ms")),
    "inp": ("ms", ("inp", "inp_ms", "interaction_to_next_paint", "interaction_to_next_paint_ms")),
    "cls": ("score", ("cls", "cumulative_layout_shift")),
    "fcp": ("ms", ("fcp", "fcp_ms", "first_contentful_paint", "first_contentful_paint_ms")),
    "ttfb": ("ms", ("ttfb", "ttfb_ms", "time_to_first_byte", "experimental_time_to_first_byte")),
}
PSI_FIELD_KEYS = {
    "LARGEST_CONTENTFUL_PAINT_MS": "lcp",
    "INTERACTION_TO_NEXT_PAINT": "inp",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
    "FIRST_CONTENTFUL_PAINT_MS": "fcp",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb",
}
LIGHTHOUSE_AUDITS = {
    "largest-contentful-paint": "lcp",
    "interaction-to-next-paint": "inp",
    "experimental-interaction-to-next-paint": "inp",
    "cumulative-layout-shift": "cls",
    "first-contentful-paint": "fcp",
    "server-response-time": "server_response_time",
    "speed-index": "speed_index",
    "total-blocking-time": "total_blocking_time",
}
LIGHTHOUSE_OPPORTUNITIES = (
    "render-blocking-resources", "unused-javascript", "unused-css-rules",
    "modern-image-formats", "uses-responsive-images", "uses-optimized-images",
    "offscreen-images", "legacy-javascript", "third-party-summary",
)
TEMPLATE_FAMILY_PRIORITY = (
    "homepage", "money_page", "service_page", "product_page", "collection_page",
    "location_landing", "comparison_page", "article", "blog", "utility", "unknown",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number < 0 or number != number or number in {float("inf"), float("-inf")} else number


def _unit_interval(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number <= 1 else None


def _provider_state(state: Any) -> tuple[str, str | None]:
    normalized = _text(state).lower()
    if normalized in PROVIDER_STATES:
        return normalized, None
    return "unavailable", "provider_state_invalid"


def _rating(value: Any) -> str | None:
    value = _text(value).lower().replace("-", "_").replace(" ", "_")
    value = {"fast": "good", "average": "needs_improvement", "slow": "poor"}.get(value, value)
    return value if value in {"good", "needs_improvement", "poor"} else None


def _metric(value: Any, unit: str) -> dict[str, Any] | None:
    rating, raw = None, value
    if isinstance(value, dict):
        rating = _rating(value.get("rating") or value.get("category"))
        percentiles = value.get("percentiles") if isinstance(value.get("percentiles"), dict) else {}
        raw = value.get("p75", value.get("percentile", percentiles.get("p75", value.get("value"))))
    numeric = _number(raw)
    return None if numeric is None else {"value": numeric, "unit": unit, "rating": rating}


def _metrics(values: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(values, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for canonical, (unit, aliases) in FIELD_METRICS.items():
        for alias in aliases:
            item = _metric(values.get(alias), unit) if alias in values else None
            if item is not None:
                result[canonical] = item
                break
    return result


def normalize_field_performance_evidence(*, provider: str, state: str,
    metrics: dict[str, Any] | None = None, scope: str | None = None,
    observed_at: str | None = None, source_url: str | None = None,
    reason: str | None = None) -> dict[str, Any]:
    """Normalize field evidence; non-connected states never retain metrics."""
    normalized_state, invalid_reason = _provider_state(state)
    base = {
        "version": FIELD_PERFORMANCE_VERSION, "evidence_kind": "field",
        "provider": _text(provider) or "unknown", "state": normalized_state,
        "reason": _text(reason) or invalid_reason, "scope": _text(scope) or None,
        "observed_at": _text(observed_at) or None, "source_url": _text(source_url) or None,
        "metrics": None,
    }
    if normalized_state != "connected":
        return base
    normalized = _metrics(metrics)
    return {**base, "metrics": normalized} if normalized else {
        **base, "state": "unavailable", "reason": _text(reason) or "field_metrics_unavailable"
    }


def normalize_crux_evidence(payload: dict[str, Any] | None, *, state: str = "connected",
    observed_at: str | None = None, scope: str | None = None,
    source_url: str | None = None, reason: str | None = None) -> dict[str, Any]:
    """Normalize a CrUX-style payload into the field contract."""
    provider_state, invalid_reason = _provider_state(state)
    if provider_state != "connected":
        return normalize_field_performance_evidence(
            provider="CrUX", state=provider_state, scope=scope, observed_at=observed_at,
            source_url=source_url, reason=reason or invalid_reason,
        )
    if not isinstance(payload, dict):
        return normalize_field_performance_evidence(
            provider="CrUX", state="unavailable", scope=scope, observed_at=observed_at,
            source_url=source_url, reason=reason or "provider_payload_missing",
        )
    values = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
    return normalize_field_performance_evidence(
        provider="CrUX", state="connected", metrics=values,
        scope=scope or _text(payload.get("scope")) or None,
        observed_at=observed_at or _text(payload.get("observed_at")) or None,
        source_url=source_url, reason=reason,
    )


def normalize_lighthouse_evidence(payload: dict[str, Any] | None, *, provider: str = "Lighthouse",
    state: str = "connected", observed_at: str | None = None,
    source_url: str | None = None, reason: str | None = None) -> dict[str, Any]:
    """Normalize bounded lab evidence from Lighthouse JSON."""
    normalized_state, invalid_reason = _provider_state(state)
    base = {
        "version": LIGHTHOUSE_EVIDENCE_VERSION, "evidence_kind": "lab",
        "provider": _text(provider) or "Lighthouse", "state": normalized_state,
        "reason": _text(reason) or invalid_reason, "observed_at": _text(observed_at) or None,
        "source_url": _text(source_url) or None, "performance_score": None,
        "metrics": None, "opportunities": [],
    }
    if normalized_state != "connected":
        return base
    if not isinstance(payload, dict):
        return {**base, "state": "unavailable", "reason": _text(reason) or "lighthouse_payload_missing"}
    categories = payload.get("categories") if isinstance(payload.get("categories"), dict) else {}
    performance = categories.get("performance") if isinstance(categories.get("performance"), dict) else {}
    score = _unit_interval(performance.get("score"))
    score = round(score * 100, 1) if score is not None else None
    audits = payload.get("audits") if isinstance(payload.get("audits"), dict) else {}
    metrics: dict[str, dict[str, Any]] = {}
    for audit_id, canonical in LIGHTHOUSE_AUDITS.items():
        audit = audits.get(audit_id)
        value = _number(audit.get("numericValue")) if isinstance(audit, dict) else None
        if value is not None:
            metrics[canonical] = {
                "value": value,
                "unit": _text(audit.get("numericUnit")) or None,
                "score": _unit_interval(audit.get("score")),
            }
    opportunities = []
    for audit_id in LIGHTHOUSE_OPPORTUNITIES:
        audit = audits.get(audit_id)
        if not isinstance(audit, dict):
            continue
        details = audit.get("details") if isinstance(audit.get("details"), dict) else {}
        savings_ms = _number(details.get("overallSavingsMs"))
        if savings_ms is None:
            savings_ms = _number(audit.get("numericValue"))
        savings_bytes = _number(details.get("overallSavingsBytes"))
        audit_score = _unit_interval(audit.get("score"))
        if savings_ms is not None or savings_bytes is not None or audit_score is not None:
            opportunities.append({
                "audit_id": audit_id,
                "score": audit_score,
                "estimated_savings_ms": savings_ms,
                "estimated_savings_bytes": savings_bytes,
            })
    if score is None and not metrics and not opportunities:
        return {**base, "state": "unavailable", "reason": _text(reason) or "lighthouse_measurements_unavailable"}
    return {**base, "performance_score": score, "metrics": metrics or None, "opportunities": opportunities}


def _psi_field(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    experience, scope = payload.get("loadingExperience"), "url"
    if not isinstance(experience, dict) or not isinstance(experience.get("metrics"), dict):
        experience, scope = payload.get("originLoadingExperience"), "origin"
    if not isinstance(experience, dict) or not isinstance(experience.get("metrics"), dict):
        return None, None
    mapped: dict[str, Any] = {}
    for raw_key, canonical in PSI_FIELD_KEYS.items():
        item = experience["metrics"].get(raw_key)
        if not isinstance(item, dict):
            continue
        percentile = item.get("percentile")
        if canonical == "cls" and _number(percentile) is not None:
            percentile = float(percentile) / 100.0
        mapped[canonical] = {"p75": percentile, "rating": item.get("category")}
    return mapped, scope


def normalize_pagespeed_insights_evidence(payload: dict[str, Any] | None, *, state: str = "connected",
    observed_at: str | None = None, source_url: str | None = None,
    reason: str | None = None) -> dict[str, Any]:
    """Normalize PSI while keeping CrUX field and Lighthouse lab evidence distinct."""
    provider_state, invalid_reason = _provider_state(state)
    if provider_state != "connected" or not isinstance(payload, dict):
        if provider_state == "connected":
            state_out, why = "unavailable", reason or "provider_payload_missing"
        else:
            state_out, why = provider_state, reason or invalid_reason
        return {
            "version": PERFORMANCE_EVIDENCE_VERSION,
            "provider": "PageSpeed Insights",
            "field": normalize_field_performance_evidence(
                provider="PageSpeed Insights / CrUX", state=state_out,
                observed_at=observed_at, source_url=source_url, reason=why,
            ),
            "lab": normalize_lighthouse_evidence(
                None, provider="PageSpeed Insights / Lighthouse", state=state_out,
                observed_at=observed_at, source_url=source_url, reason=why,
            ),
        }
    field_values, field_scope = _psi_field(payload)
    field = normalize_field_performance_evidence(
        provider="PageSpeed Insights / CrUX",
        state="connected" if field_values else "unavailable",
        metrics=field_values, scope=field_scope,
        observed_at=observed_at, source_url=source_url,
        reason=None if field_values else "crux_field_data_unavailable",
    )
    lighthouse = payload.get("lighthouseResult") if isinstance(payload.get("lighthouseResult"), dict) else None
    lab = normalize_lighthouse_evidence(
        lighthouse, provider="PageSpeed Insights / Lighthouse",
        state="connected" if lighthouse else "unavailable", observed_at=observed_at,
        source_url=source_url, reason=None if lighthouse else "lighthouse_lab_data_unavailable",
    )
    return {"version": PERFORMANCE_EVIDENCE_VERSION, "provider": "PageSpeed Insights", "field": field, "lab": lab}


def _normalized_url(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")) if parsed.scheme and parsed.netloc else raw
    except Exception:
        return raw


def _url(page: dict[str, Any]) -> str:
    return _normalized_url(page.get("final_url") or page.get("url")) or ""


def _eligible(page: Any) -> bool:
    if not isinstance(page, dict) or not _url(page) or _text(page.get("fetch_error")):
        return False
    status = page.get("status_code")
    if isinstance(status, int) and not 200 <= status < 400:
        return False
    return _text(page.get("page_evidence_class")) in {"", "usable_html"}


def _family(page: dict[str, Any]) -> str:
    return _text(page.get("page_template_family") or page.get("template_family") or page.get("page_type")).lower() or "unknown"


def _weight(page: dict[str, Any]) -> float:
    for key in ("performance_sample_weight", "high_value_score", "page_value_score", "page_value"):
        value = _number(page.get(key))
        if value is not None:
            return value
    if page.get("is_high_value") is True:
        return 1.0
    return 0.9 if _text(page.get("page_role") or page.get("intent")).lower() in {"money", "transactional", "conversion", "revenue"} else 0.0


def _family_rank(family: str) -> int:
    try:
        return TEMPLATE_FAMILY_PRIORITY.index(family)
    except ValueError:
        return len(TEMPLATE_FAMILY_PRIORITY)


def _candidate_rank(page: dict[str, Any]) -> tuple[Any, ...]:
    family = _family(page)
    return (-_weight(page), _family_rank(family), family, _url(page))


def select_representative_performance_pages(pages: Iterable[dict[str, Any]], *, max_pages: int = 8) -> dict[str, Any]:
    """Take one page per template first, then high-value fills; hard-cap browser work."""
    requested = max(0, int(max_pages or 0))
    limit = min(requested, MAX_PERFORMANCE_SAMPLE_PAGES)
    unique: dict[str, dict[str, Any]] = {}
    eligible_observations = 0
    for page in pages:
        if not _eligible(page):
            continue
        eligible_observations += 1
        key = _url(page)
        current = unique.get(key)
        if current is None or _candidate_rank(page) < _candidate_rank(current):
            unique[key] = page
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in unique.values():
        grouped[_family(page)].append(page)
    for family_pages in grouped.values():
        family_pages.sort(key=_candidate_rank)
    families = sorted(grouped, key=lambda f: (-max((_weight(p) for p in grouped[f]), default=0.0), _family_rank(f), f))
    selected: list[dict[str, Any]] = []
    for family in families[:limit]:
        selected.append(grouped[family][0])
    selected_urls = {_url(page) for page in selected}
    if len(selected) < limit:
        rest = [page for family_pages in grouped.values() for page in family_pages if _url(page) not in selected_urls]
        rest.sort(key=lambda p: (-_weight(p), _family_rank(_family(p)), _family(p), _url(p)))
        selected.extend(rest[: limit - len(selected)])
    rows = [{
        "url": _url(page),
        "template_family": _family(page),
        "high_value_weight": _weight(page),
        "selection_reason": "template_representative" if grouped[_family(page)][0] is page else "high_value_fill",
    } for page in selected]
    covered = {row["template_family"] for row in rows}
    omitted = [family for family in families if family not in covered]
    return {
        "version": REPRESENTATIVE_SAMPLE_VERSION,
        "requested_max_pages": requested,
        "max_pages": limit,
        "hard_cap": MAX_PERFORMANCE_SAMPLE_PAGES,
        "eligible_page_observations": eligible_observations,
        "duplicate_page_observations_dropped": max(0, eligible_observations - len(unique)),
        "eligible_pages": len(unique),
        "template_families": len(grouped),
        "selected_pages": len(rows),
        "template_coverage_complete": not omitted,
        "omitted_template_families": omitted,
        "pages": rows,
    }


def _strings(value: Any) -> set[str] | None:
    if value is None or not isinstance(value, list):
        return None
    return {text for item in value if (text := _text(item.get("href") if isinstance(item, dict) else item))}


def _links(page: dict[str, Any]) -> set[str] | None:
    values = page.get("important_links")
    raw_links = _strings(values)
    if raw_links is None:
        return None
    base = _url(page)
    normalized: set[str] = set()
    for link in raw_links:
        absolute = urljoin(base, link) if base else link
        normalized.add(_normalized_url(absolute) or absolute)
    return normalized


def _schemas(page: dict[str, Any]) -> set[str] | None:
    return _strings(page.get("schema_types"))


def _facts(page: dict[str, Any]) -> dict[str, str] | None:
    result: dict[str, str] = {}
    for section in ("product_facts", "entity_facts"):
        values = page.get(section)
        if isinstance(values, dict):
            for key, value in values.items():
                if normalized := _text(value):
                    result[f"{section}.{_text(key)}"] = normalized
    return result or None


def _indexability(page: dict[str, Any]) -> str | None:
    if isinstance(page.get("indexable"), bool):
        return "indexable" if page["indexable"] else "not_indexable"
    if state := _text(page.get("indexability_state")):
        return state.lower()
    if robots := _text(page.get("meta_robots")).lower():
        return "not_indexable" if "noindex" in robots else "indexable"
    return None


def _main_present(page: dict[str, Any]) -> bool | None:
    for key in ("main_content_present", "has_main_content"):
        if isinstance(page.get(key), bool):
            return page[key]
    for key in ("main_text", "main_content"):
        if key in page:
            return bool(_text(page.get(key)))
    count = _number(page.get("word_count")) if "word_count" in page else None
    return None if count is None else count > 0


def _scalar(raw: Any, rendered: Any, normalize=lambda x: x) -> dict[str, Any]:
    raw, rendered = normalize(raw), normalize(rendered)
    if raw is None and rendered is None:
        state = "not_verified"
    elif raw is None:
        state = "raw_missing_rendered_present"
    elif rendered is None:
        state = "raw_present_rendered_missing"
    else:
        state = "same" if raw == rendered else "changed"
    return {"state": state, "raw": raw, "rendered": rendered}


def _sets(raw: set[str] | None, rendered: set[str] | None) -> dict[str, Any]:
    if raw is None or rendered is None:
        return {
            "state": "not_verified",
            "raw_count": len(raw) if raw is not None else None,
            "rendered_count": len(rendered) if rendered is not None else None,
            "rendered_only": [],
            "raw_only": [],
        }
    rendered_only, raw_only = sorted(rendered - raw), sorted(raw - rendered)
    return {
        "state": "same" if not rendered_only and not raw_only else "changed",
        "raw_count": len(raw),
        "rendered_count": len(rendered),
        "rendered_only": rendered_only[:20],
        "raw_only": raw_only[:20],
    }


def _explicitly_unusable_render(page: dict[str, Any]) -> str | None:
    if _text(page.get("fetch_error")):
        return "render_fetch_error"
    status = page.get("status_code")
    if isinstance(status, int) and not 200 <= status < 400:
        return "render_http_status_unusable"
    evidence_class = _text(page.get("page_evidence_class"))
    if evidence_class and evidence_class != "usable_html":
        return "render_evidence_class_unusable"
    return None


def compare_critical_content_parity(raw_page: dict[str, Any], rendered_page: dict[str, Any] | None, *,
    render_state: str = "completed", render_reason: str | None = None) -> dict[str, Any]:
    """Compare critical raw/rendered evidence; failed rendering is always not_verified."""
    if not isinstance(raw_page, dict):
        return {
            "version": CRITICAL_PARITY_VERSION, "url": None, "state": "not_verified",
            "reason": "raw_evidence_unavailable", "material_delta": None,
            "verified_fields": [], "changed_fields": [], "fields": {},
        }
    url = _url(raw_page)
    if render_state != "completed" or not isinstance(rendered_page, dict):
        return {
            "version": CRITICAL_PARITY_VERSION, "url": url or None, "state": "not_verified",
            "reason": _text(render_reason) or "render_evidence_unavailable", "material_delta": None,
            "verified_fields": [], "changed_fields": [], "fields": {},
        }
    if unusable_reason := _explicitly_unusable_render(rendered_page):
        return {
            "version": CRITICAL_PARITY_VERSION, "url": url or None, "state": "not_verified",
            "reason": _text(render_reason) or unusable_reason, "material_delta": None,
            "verified_fields": [], "changed_fields": [], "fields": {},
        }
    rendered_url = _url(rendered_page)
    if url and rendered_url and url != rendered_url:
        return {
            "version": CRITICAL_PARITY_VERSION, "url": url, "rendered_url": rendered_url,
            "state": "not_verified", "reason": "render_identity_mismatch", "material_delta": None,
            "verified_fields": [], "changed_fields": [], "fields": {},
        }
    fields = {
        "title": _scalar(raw_page.get("title"), rendered_page.get("title"), lambda x: _text(x) or None),
        "h1": _scalar(raw_page.get("h1"), rendered_page.get("h1"), lambda x: _text(x) or None),
        "canonical": _scalar(raw_page.get("canonical"), rendered_page.get("canonical"), _normalized_url),
        "indexability": _scalar(_indexability(raw_page), _indexability(rendered_page)),
        "main_content_present": _scalar(_main_present(raw_page), _main_present(rendered_page)),
        "important_links": _sets(_links(raw_page), _links(rendered_page)),
        "structured_data": _sets(_schemas(raw_page), _schemas(rendered_page)),
        "business_facts": _scalar(_facts(raw_page), _facts(rendered_page)),
    }
    verified_fields = sorted(name for name, row in fields.items() if row["state"] != "not_verified")
    changed_fields = sorted(name for name, row in fields.items() if row["state"] not in {"same", "not_verified"})
    delta = bool(changed_fields)
    return {
        "version": CRITICAL_PARITY_VERSION,
        "url": url or None,
        "rendered_url": rendered_url or None,
        "state": "not_verified" if not verified_fields else ("material_delta" if delta else "matched"),
        "reason": "critical_fields_unavailable" if not verified_fields else "paired_render_evidence",
        "material_delta": delta if verified_fields else None,
        "verified_fields": verified_fields,
        "changed_fields": changed_fields,
        "fields": fields,
    }
