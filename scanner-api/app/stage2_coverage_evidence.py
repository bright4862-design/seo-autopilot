"""Pure Stage-2 coverage evidence helpers for B10-B15 and B17-B18.

No helper in this module performs network I/O or mutates scanner page records.
Shared orchestration remains an integration-layer concern. Unknown or unavailable
evidence stays explicit rather than being coerced to a pass or a zero.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from hashlib import sha256
from typing import Any
import math
import re

from .stage2_reachability_provenance import (
    REACHABILITY_PROVENANCE_VERSION,
    REACHABILITY_SCOPE,
)

MAIN_TEXT_EVIDENCE_VERSION = "main_text_signature_v1"
NEAR_DUPLICATE_VERSION = "near_duplicate_main_v1"
MONEY_REACHABILITY_VERSION = "money_page_reachability_v1"
HUB_RENDER_COMPARE_VERSION = "hub_raw_rendered_links_v1"
LOCAL_ENTITY_VERSION = "local_entity_completeness_v1"
NAP_CONSISTENCY_VERSION = "local_entity_nap_consistency_v1"
FRESHNESS_VERSION = "contextual_freshness_v1"
PAGE_WEIGHT_VERSION = "page_weight_evidence_v1"
CRUX_ADAPTER_VERSION = "crux_optional_v1"
GSC_ADAPTER_VERSION = "gsc_optional_v1"

MAX_PAGES = 150
MAX_SHINGLES = 512
MAX_CLUSTER_SAMPLES = 10
MAX_HUBS = 5
MAX_LINK_SAMPLES = 20
MAX_ENTITY_SAMPLES = 20

MONEY_FAMILIES = {
    "activity_detail",
    "product_page",
    "product_detail",
    "calculator",
    "conversion",
    "booking_or_checkout",
    "loan_program",
    "pricing_page",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _page_url(page: dict[str, Any]) -> str:
    return _clean(page.get("url") or page.get("final_url") or page.get("page_url"))


def _bounded_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if (
        not isinstance(pages, list)
        or len(pages) > MAX_PAGES
        or any(not isinstance(page, dict) for page in pages)
    ):
        raise ValueError("Expected at most 150 page objects")
    return pages


def _verified_html(page: dict[str, Any]) -> bool:
    return (
        page.get("page_evidence_class") == "usable_html"
        and 200 <= int(page.get("status_code") or 0) < 300
        and not page.get("fetch_error")
        and not page.get("raw_html_truncated")
    )


def _main_tokens(page: dict[str, Any]) -> list[str]:
    if not _verified_html(page):
        return []
    if page.get("main_text_evidence_version") != MAIN_TEXT_EVIDENCE_VERSION:
        return []
    if page.get("main_text_verified") is not True:
        return []
    return re.findall(r"[\w'-]+", _clean(page.get("main_text")).lower(), flags=re.UNICODE)


def _signature(tokens: list[str], shingle_size: int = 5) -> tuple[list[str], str]:
    if len(tokens) < shingle_size:
        return [], ""
    shingles: list[str] = []
    seen: set[str] = set()
    for index in range(len(tokens) - shingle_size + 1):
        raw = "\x1f".join(tokens[index : index + shingle_size])
        digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
        if digest not in seen:
            seen.add(digest)
            shingles.append(digest)
        if len(shingles) >= MAX_SHINGLES:
            break
    aggregate = sha256("|".join(shingles).encode("ascii")).hexdigest() if shingles else ""
    return shingles, aggregate


def near_duplicate_main_content(
    pages: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.82,
    min_tokens: int = 40,
) -> dict[str, Any]:
    """Cluster only verified main-content shingles, never chrome/template text."""
    pages = _bounded_pages(pages)
    if not 0.5 <= float(similarity_threshold) <= 1.0:
        raise ValueError("similarity_threshold out of bounds")

    rows: list[dict[str, Any]] = []
    for page in pages:
        tokens = _main_tokens(page)
        if len(tokens) < min_tokens:
            continue
        shingles, digest = _signature(tokens)
        if not shingles:
            continue
        rows.append(
            {
                "url": _page_url(page),
                "family": _clean(page.get("page_template_family") or "standard"),
                "shingles": frozenset(shingles),
                "signature": digest,
            }
        )

    parent = list(range(len(rows)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    pair_samples: list[dict[str, Any]] = []
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            union = rows[left]["shingles"] | rows[right]["shingles"]
            similarity = (
                len(rows[left]["shingles"] & rows[right]["shingles"]) / len(union)
                if union
                else 0.0
            )
            if similarity < similarity_threshold:
                continue
            left_root, right_root = root(left), root(right)
            if left_root != right_root:
                parent[right_root] = left_root
            if len(pair_samples) < MAX_CLUSTER_SAMPLES:
                pair_samples.append(
                    {
                        "left": rows[left]["url"],
                        "right": rows[right]["url"],
                        "similarity": round(similarity, 4),
                    }
                )

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[root(index)].append(row)

    clusters: list[dict[str, Any]] = []
    for members in grouped.values():
        if len(members) < 2:
            continue
        urls = [member["url"] for member in members]
        clusters.append(
            {
                "cluster_id": "dup_" + sha256("|".join(sorted(urls)).encode()).hexdigest()[:12],
                "page_count": len(urls),
                "representative_url": urls[0],
                "affected_pages": urls[:MAX_CLUSTER_SAMPLES],
                "affected_pages_truncated": len(urls) > MAX_CLUSTER_SAMPLES,
                "families": sorted({member["family"] for member in members}),
                "content_signatures": [
                    member["signature"] for member in members[:MAX_CLUSTER_SAMPLES]
                ],
            }
        )

    state = "not_verified" if not rows else ("fail" if clusters else "pass")
    reason = (
        "verified_main_text_unavailable"
        if not rows
        else ("near_duplicate_main_content_observed" if clusters else "no_near_duplicate_cluster_observed")
    )
    return {
        "version": NEAR_DUPLICATE_VERSION,
        "state": state,
        "reason": reason,
        "eligible_pages": len(rows),
        "clusters": clusters,
        "pair_samples": pair_samples,
    }


def money_page_reachability(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize B11 observed reachability without a sitewide orphan claim.

    Only the versioned producer envelope is accepted. A sitemap source or legacy
    ``source_pages`` value is not silently promoted into an internal inlink.
    Verified weak signals may fail inside the observed sample; partial provenance
    remains unknown, and a pass requires all three B11 dimensions to be known.
    """
    pages = _bounded_pages(pages)
    rows: list[dict[str, Any]] = []
    for page in pages:
        family = _clean(page.get("page_template_family")).lower()
        if not (page.get("money_page") is True or family in MONEY_FAMILIES):
            continue

        provenance_ok = (
            page.get("reachability_provenance_version") == REACHABILITY_PROVENANCE_VERSION
            and page.get("reachability_scope") == REACHABILITY_SCOPE
            and page.get("reachability_evidence_state") == "observed_sample"
            and page.get("sitewide_orphan_claim") is False
        )
        if not provenance_ok:
            rows.append(
                {
                    "url": _page_url(page),
                    "family": family or "standard",
                    "observed_inlinks": None,
                    "source_samples": [],
                    "observed_depth": None,
                    "navigation_presence": None,
                    "state": "not_verified",
                    "reason": "reachability_provenance_unavailable",
                    "sitewide_orphan_claim": False,
                }
            )
            continue

        raw_sources = page.get("internal_source_pages")
        sources = raw_sources if isinstance(raw_sources, list) else []
        unique_sources = [source for source in dict.fromkeys(_clean(v) for v in sources) if source]
        observed_inlinks = page.get("observed_internal_inlink_count")
        if not isinstance(observed_inlinks, int) or observed_inlinks < 0:
            observed_inlinks = None
        elif observed_inlinks != len(unique_sources) and page.get("internal_source_pages_truncated") is not True:
            # Exact counts and examples must agree unless the examples are
            # explicitly truncated. Mismatched evidence fails closed.
            observed_inlinks = None

        depth = page.get("crawl_depth")
        depth = int(depth) if isinstance(depth, int) and 0 <= depth <= MAX_PAGES else None
        nav = page.get("navigation_presence")
        nav_state = nav if type(nav) is bool else None

        weak = (
            observed_inlinks == 0
            or (depth is not None and depth >= 4)
            or nav_state is False
        )
        complete = observed_inlinks is not None and depth is not None and nav_state is not None
        if weak:
            state, reason = "fail", "weak_route_in_observed_sample"
        elif complete:
            state, reason = "pass", "reachable_in_observed_sample"
        else:
            state, reason = "not_verified", "reachability_evidence_partial"

        rows.append(
            {
                "url": _page_url(page),
                "family": family or "standard",
                "observed_inlinks": observed_inlinks,
                "source_samples": unique_sources[:MAX_LINK_SAMPLES],
                "source_samples_truncated": page.get("internal_source_pages_truncated") is True,
                "observed_depth": depth,
                "navigation_presence": nav_state,
                "state": state,
                "reason": reason,
                "sitewide_orphan_claim": False,
            }
        )

    if not rows:
        overall_state = "not_verified"
    elif any(row["state"] == "fail" for row in rows):
        overall_state = "fail"
    elif any(row["state"] == "not_verified" for row in rows):
        overall_state = "not_verified"
    else:
        overall_state = "pass"
    return {
        "version": MONEY_REACHABILITY_VERSION,
        "provenance_version": REACHABILITY_PROVENANCE_VERSION,
        "scope": REACHABILITY_SCOPE,
        "state": overall_state,
        "money_pages_observed": len(rows),
        "weak_routes": sum(1 for row in rows if row["state"] == "fail"),
        "unverified_routes": sum(1 for row in rows if row["state"] == "not_verified"),
        "sitewide_orphan_claim": False,
        "pages": rows,
    }


def compare_raw_rendered_hub_links(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(pairs, list):
        raise ValueError("Expected paired hub observations")
    selected = pairs[:MAX_HUBS]
    results: list[dict[str, Any]] = []
    for pair in selected:
        if not isinstance(pair, dict):
            raise ValueError("Malformed hub pair")
        url = _clean(pair.get("hub_url"))
        if pair.get("raw_success") is not True or pair.get("rendered_success") is not True:
            results.append(
                {
                    "hub_url": url,
                    "state": "not_verified",
                    "reason": "raw_or_rendered_pair_failed",
                    "raw_link_count": None,
                    "rendered_link_count": None,
                    "render_only_samples": [],
                    "raw_only_samples": [],
                }
            )
            continue
        raw = {_clean(value) for value in pair.get("raw_links", []) if _clean(value)}
        rendered = {_clean(value) for value in pair.get("rendered_links", []) if _clean(value)}
        results.append(
            {
                "hub_url": url,
                "state": "pass",
                "reason": "paired_successful_evidence",
                "raw_link_count": len(raw),
                "rendered_link_count": len(rendered),
                "render_only_count": len(rendered - raw),
                "raw_only_count": len(raw - rendered),
                "render_only_samples": sorted(rendered - raw)[:MAX_LINK_SAMPLES],
                "raw_only_samples": sorted(raw - rendered)[:MAX_LINK_SAMPLES],
            }
        )
    return {
        "version": HUB_RENDER_COMPARE_VERSION,
        "selected": len(selected),
        "completed": sum(1 for row in results if row["state"] == "pass"),
        "failed": sum(1 for row in results if row["state"] == "not_verified"),
        "unassessed": max(0, len(pairs) - len(selected)),
        "hubs": results,
    }


def assess_local_entity_completeness(observation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(observation, dict):
        raise ValueError("Expected local entity observation")
    if observation.get("applicable") is not True:
        return {
            "version": LOCAL_ENTITY_VERSION,
            "state": "not_applicable" if observation.get("applicable") is False else "not_verified",
            "reason": observation.get("reason") or "local_entity_applicability_unknown",
            "missing_required": [],
            "unverified_fields": [],
        }
    if observation.get("accepted") is not True:
        return {
            "version": LOCAL_ENTITY_VERSION,
            "state": "not_verified",
            "reason": observation.get("reason") or "local_entity_evidence_unavailable",
            "missing_required": [],
            "unverified_fields": [],
        }

    contextual_status = _clean(observation.get("contextual_status")) or None
    required = ("name", "address", "phone")
    missing = [key for key in required if not _clean(observation.get(key))]
    hours = _clean(observation.get("regular_hours"))
    hours_applicable = observation.get("regular_hours_applicable")
    unverified_fields: list[str] = []
    if hours_applicable is True and not hours:
        missing.append("regular_hours")
    elif hours_applicable is not False and not hours:
        # A Coming Soon/closed/preopening context may legitimately lack regular
        # hours. Without explicit applicability, preserve this as unknown rather
        # than manufacturing a customer defect.
        unverified_fields.append("regular_hours")

    if missing:
        state, reason = "fail", "required_local_details_missing"
    elif unverified_fields:
        state, reason = "not_verified", "local_detail_applicability_unverified"
    else:
        state, reason = "pass", "required_local_details_observed"
    return {
        "version": LOCAL_ENTITY_VERSION,
        "state": state,
        "reason": reason,
        "missing_required": missing,
        "unverified_fields": unverified_fields,
        "contextual_status": contextual_status,
        "optional_available": {
            key: bool(observation.get(key))
            for key in ("holiday_hours", "photos", "same_as", "parent_entity")
        },
    }


def _norm_name(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", _clean(value).casefold()).strip()


def _norm_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", _clean(value))
    return digits[-10:] if len(digits) >= 10 else digits


def _norm_address(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", _clean(value).casefold()).strip()


def assess_nap_consistency(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(observations, list) or len(observations) > MAX_ENTITY_SAMPLES:
        raise ValueError("Expected bounded entity observations")
    accepted = [
        row
        for row in observations
        if isinstance(row, dict)
        and row.get("accepted") is True
        and _clean(row.get("entity_key"))
        and row.get("entity_match") == "verified"
    ]
    ambiguous = sum(
        1
        for row in observations
        if isinstance(row, dict) and row.get("entity_match") in {"ambiguous", "unverified"}
    )
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        groups[_clean(row["entity_key"])].append(row)
    inconsistencies: list[dict[str, Any]] = []
    for entity_key, rows in groups.items():
        values = {
            "name": {_norm_name(row.get("name")) for row in rows if _norm_name(row.get("name"))},
            "address": {_norm_address(row.get("address")) for row in rows if _norm_address(row.get("address"))},
            "phone": {_norm_phone(row.get("phone")) for row in rows if _norm_phone(row.get("phone"))},
        }
        differing = [key for key, field_values in values.items() if len(field_values) > 1]
        if differing:
            inconsistencies.append(
                {
                    "entity_key": entity_key,
                    "fields": differing,
                    "source_count": len(rows),
                    "provenance": sorted(
                        {_clean(row.get("source")) for row in rows if _clean(row.get("source"))}
                    ),
                }
            )
    return {
        "version": NAP_CONSISTENCY_VERSION,
        "state": "fail" if inconsistencies else ("pass" if accepted else "not_verified"),
        "verified_observations": len(accepted),
        "ambiguous_observations": ambiguous,
        "inconsistencies": inconsistencies,
    }


def _date_value(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    raw = _clean(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def assess_contextual_freshness(
    page: dict[str, Any],
    *,
    as_of: date,
    max_current_age_days: int = 550,
) -> dict[str, Any]:
    intent = _clean(page.get("current_content_intent"))
    intent_evidence = page.get("current_content_intent_evidence")
    temporal = page.get("temporal_evidence")
    if not intent or not isinstance(intent_evidence, list) or not intent_evidence:
        return {"version": FRESHNESS_VERSION, "state": "not_applicable", "reason": "no_current_content_intent"}
    if not isinstance(temporal, list) or not temporal:
        return {"version": FRESHNESS_VERSION, "state": "not_verified", "reason": "temporal_evidence_unavailable"}
    dates = [
        parsed
        for row in temporal
        if isinstance(row, dict)
        for parsed in [_date_value(row.get("date"))]
        if parsed is not None and row.get("scope") == "current"
    ]
    if not dates:
        return {"version": FRESHNESS_VERSION, "state": "not_verified", "reason": "no_current_scope_date"}
    latest = max(dates)
    age_days = max(0, (as_of - latest).days)
    stale = age_days > int(max_current_age_days)
    return {
        "version": FRESHNESS_VERSION,
        "state": "fail" if stale else "pass",
        "reason": "current_intent_conflicts_with_old_temporal_evidence" if stale else "current_intent_temporal_evidence_consistent",
        "latest_current_scope_date": latest.isoformat(),
        "age_days": age_days,
        "intent": intent,
    }


def optional_crux_adapter(
    *,
    connection_state: str,
    observed_at: date | None = None,
    as_of: date | None = None,
    scope: str = "",
    metrics: dict[str, Any] | None = None,
    max_age_days: int = 35,
) -> dict[str, Any]:
    if connection_state not in {"connected", "disconnected", "unavailable"}:
        raise ValueError("Invalid CrUX connection state")
    base = {
        "version": CRUX_ADAPTER_VERSION,
        "provider": "CrUX",
        "scope": _clean(scope) or None,
        "state": connection_state,
        "observed_at": observed_at.isoformat() if observed_at else None,
        "metrics": None,
    }
    if connection_state != "connected":
        return base
    if not observed_at or not as_of:
        return {**base, "state": "unavailable"}
    if observed_at > as_of:
        return {
            **base,
            "state": "unavailable",
            "reason": "provider_observation_time_invalid",
        }
    if (as_of - observed_at).days > max_age_days:
        return {**base, "state": "stale"}
    if not isinstance(metrics, dict):
        return {**base, "state": "unavailable"}
    safe: dict[str, Any] = {}
    for key in ("lcp_ms", "inp_ms", "cls"):
        value = metrics.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            safe[key] = value
    return {**base, "state": "connected" if safe else "unavailable", "metrics": safe or None}


def page_weight_evidence(
    *,
    decoded_bytes: int | None,
    inline_script_bytes: int | None,
    inline_style_bytes: int | None,
    transfer_bytes: int | None = None,
    transfer_measured: bool = False,
    crux: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def nonnegative(value: int | None) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None

    decoded = nonnegative(decoded_bytes)
    scripts = nonnegative(inline_script_bytes)
    styles = nonnegative(inline_style_bytes)
    transfer = nonnegative(transfer_bytes) if transfer_measured else None
    return {
        "version": PAGE_WEIGHT_VERSION,
        "state": "pass" if any(value is not None for value in (decoded, scripts, styles, transfer)) else "not_verified",
        "transfer_bytes": transfer,
        "transfer_bytes_state": "measured" if transfer is not None else "unknown",
        "decoded_bytes": decoded,
        "inline_script_bytes": scripts,
        "inline_style_bytes": styles,
        "crux": crux
        if isinstance(crux, dict)
        else {
            "version": CRUX_ADAPTER_VERSION,
            "provider": "CrUX",
            "state": "disconnected",
            "scope": None,
            "observed_at": None,
            "metrics": None,
        },
    }


def optional_gsc_adapter(
    *,
    connection_state: str,
    as_of: date,
    observed_at: date | None = None,
    metrics: dict[str, Any] | None = None,
    max_age_days: int = 8,
) -> dict[str, Any]:
    if connection_state not in {"connected", "disconnected", "unavailable"}:
        raise ValueError("Invalid GSC connection state")
    base = {
        "version": GSC_ADAPTER_VERSION,
        "provider": "Google Search Console",
        "state": connection_state,
        "observed_at": observed_at.isoformat() if observed_at else None,
        "metrics": None,
    }
    if connection_state != "connected":
        return base
    if not observed_at:
        return {**base, "state": "unavailable"}
    if observed_at > as_of:
        return {
            **base,
            "state": "unavailable",
            "reason": "provider_observation_time_invalid",
        }
    if (as_of - observed_at).days > max_age_days:
        return {**base, "state": "stale"}
    if not isinstance(metrics, dict):
        return {**base, "state": "unavailable"}
    safe: dict[str, Any] = {}
    for key in ("clicks", "impressions", "position"):
        value = metrics.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            safe[key] = value
    if metrics.get("index_state") in {"indexed", "not_indexed", "unknown"}:
        safe["index_state"] = metrics["index_state"]
    return {**base, "state": "connected" if safe else "unavailable", "metrics": safe or None}
