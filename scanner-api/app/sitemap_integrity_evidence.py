from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable
from urllib.parse import urlsplit


SITEMAP_INTEGRITY_EVIDENCE_VERSION = "sitemap_integrity_probe_v1_shared_scheduler"
_ACCESS_LIMIT_STATUSES = {401, 403, 407, 408, 425, 429}
_MISSING_STATUSES = {404, 410}


def _clean(value: Any, width: int = 2_000) -> str:
    return str(value or "").strip()[:width]


def _origin_key(url: str) -> str:
    parsed = urlsplit(_clean(url))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _scope_prefix(value: str) -> str:
    raw = _clean(value) or "/"
    path = urlsplit(raw).path if raw.startswith(("http://", "https://")) else raw
    path = "/" + path.strip("/") if path and path != "/" else "/"
    return path.rstrip("/") if path != "/" else "/"


def _path_within_scope(path: str, prefix: str) -> bool:
    clean = "/" + str(path or "/").lstrip("/")
    base = _scope_prefix(prefix)
    return base == "/" or clean == base or clean.startswith(base + "/")


def _status(page: Any) -> int:
    if not isinstance(page, dict):
        return 0
    try:
        return max(0, int(page.get("status_code") or 0))
    except (TypeError, ValueError):
        return 0


def _access_kind(page: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return _clean(page.get("access_block_kind"), 100).lower()


def _fetch_error(page: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return _clean(page.get("fetch_error"), 220)


def _final_url(page: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return _clean(page.get("final_url") or page.get("url") or page.get("request_url"))


def _complete_usable_html(page: Any) -> bool:
    if not isinstance(page, dict):
        return False
    status = _status(page)
    if not 200 <= status < 300 or _fetch_error(page):
        return False
    if page.get("raw_html_truncated") is True:
        return False
    evidence_class = _clean(page.get("page_evidence_class"), 100)
    if evidence_class and evidence_class != "usable_html":
        return False
    content_type = _clean(page.get("content_type"), 120).lower()
    if content_type and "html" not in content_type:
        return False
    if _access_kind(page) in {"challenge", "block", "rate_limit"}:
        return False
    return True


def _is_noindex(page: Any) -> bool:
    if not isinstance(page, dict):
        return False
    if page.get("noindex") is True:
        return True
    robots = _clean(page.get("robots_indexability_status"), 120).lower()
    state = _clean(page.get("indexability_state"), 120).lower()
    return robots == "noindex" or state == "noindex" or "noindex" in state


def _is_explicit_app_shell(page: Any) -> bool:
    if not isinstance(page, dict):
        return False
    if page.get("app_shell_detected") is True or page.get("client_shell_only") is True:
        return True
    evidence_class = _clean(page.get("page_evidence_class"), 100).lower()
    return evidence_class in {"app_shell", "client_shell", "client_shell_only"}


def _candidate_metadata(source_url: str, scope_prefix: str) -> dict[str, Any]:
    return {
        "synthetic": False,
        "probe_kind": "sitemap_target",
        "representative_path": _clean(source_url, 500),
        "scope_prefix": _scope_prefix(scope_prefix),
    }


def register_sitemap_target_candidates(
    scheduler,
    entries: Iterable[Any],
    *,
    assessed_urls: Iterable[str],
    origin: str,
    scope_prefix: str = "/",
    max_candidates: int = 12,
) -> dict[str, Any]:
    """Register unsampled same-site sitemap targets in the shared probe pool.

    Multiple sitemap sources for the same target are retained as bounded source
    provenance on the single deduplicated request identity. This helper declares
    candidates only; it does not fetch, mutate assessed pages or own a budget.
    """
    assessed = {_clean(value) for value in assessed_urls if _clean(value)}
    base_origin = _origin_key(origin)
    prefix = _scope_prefix(scope_prefix)
    limit = max(0, min(100, int(max_candidates or 0)))
    skipped_assessed = 0
    skipped_scope = 0
    skipped_invalid = 0
    sources_by_url: dict[str, list[str]] = defaultdict(list)

    for item in entries:
        if isinstance(item, dict):
            url = _clean(item.get("url"))
            source = _clean(item.get("sitemap_url") or item.get("source_url") or item.get("declared_source"))
        else:
            url = _clean(item)
            source = ""
        if not url:
            continue
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            skipped_invalid += 1
            continue
        if not base_origin or _origin_key(url) != base_origin or not _path_within_scope(parsed.path, prefix):
            skipped_scope += 1
            continue
        if url in assessed:
            skipped_assessed += 1
            continue
        if source and source not in sources_by_url[url]:
            sources_by_url[url].append(source)
        else:
            sources_by_url.setdefault(url, [])

    selected_urls = sorted(sources_by_url)[:limit]
    for url in selected_urls:
        sources = sorted(sources_by_url[url])
        scheduler.register(
            purpose="sitemap_target",
            url=url,
            source_pages=sources,
            metadata=_candidate_metadata(sources[0] if sources else url, prefix),
        )

    return {
        "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
        "origin": base_origin,
        "scope_prefix": prefix,
        "registered": len(selected_urls),
        "eligible_unsampled": len(sources_by_url),
        "truncated": len(sources_by_url) > len(selected_urls),
        "skipped_assessed": skipped_assessed,
        "skipped_outside_scope": skipped_scope,
        "skipped_invalid": skipped_invalid,
        "assessed_page_count_unchanged": True,
    }


def classify_sitemap_target(
    page: Any,
    *,
    requested_url: str,
    sitemap_sources: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Classify one target while preserving access-limited states as unknown."""
    requested = _clean(requested_url)
    status = _status(page)
    access_kind = _access_kind(page)
    fetch_error = _fetch_error(page)
    final = _final_url(page)
    sources = []
    for source in sitemap_sources or []:
        clean = _clean(source)
        if clean and clean not in sources:
            sources.append(clean)
        if len(sources) >= 8:
            break
    base = {
        "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
        "rule": "sitemap_integrity",
        "requested_url": requested,
        "final_url": final,
        "sitemap_sources": sources,
        "provenance": "robots_declared_or_discovered_sitemap_target_probe",
        "status_code": status,
        "state": "not_verified",
        "reason": "response_unverified",
    }

    if not isinstance(page, dict):
        return base
    if access_kind in {"challenge", "block", "rate_limit"} or status in _ACCESS_LIMIT_STATUSES:
        return {**base, "reason": access_kind or f"http_{status}"}
    if status <= 0 or fetch_error:
        return {**base, "reason": fetch_error or "request_unverified"}
    if status in _MISSING_STATUSES:
        return {**base, "state": "fail", "reason": f"sitemap_target_http_{status}"}
    if status >= 500:
        return {**base, "state": "fail", "reason": f"sitemap_target_http_{status}"}
    if 300 <= status < 400:
        return {**base, "state": "fail", "reason": "sitemap_target_redirect_response"}
    if _is_explicit_app_shell(page):
        return {**base, "state": "fail", "reason": "sitemap_target_app_shell"}
    if _is_noindex(page):
        return {**base, "state": "fail", "reason": "sitemap_target_noindex"}
    redirect_hops = int(page.get("redirect_hop_count") or 0)
    if redirect_hops > 0 or (final and requested and final != requested):
        return {**base, "state": "fail", "reason": "sitemap_target_redirected"}
    if not _complete_usable_html(page):
        return {**base, "reason": _clean(page.get("page_evidence_class"), 120) or "incomplete_response"}
    return {**base, "state": "pass", "reason": "sitemap_target_usable_indexable_html"}


def _source_failure_state(reason: str) -> tuple[str, str]:
    clean = _clean(reason, 160).lower()
    if not clean:
        return "not_verified", "sitemap_source_retrieval_failed_reason_unattributed"
    if clean in {
        "challenge",
        "block",
        "rate_limit",
        "robots_denied",
        "deadline_exhausted",
        "request_budget_exhausted",
        "timeout",
        "dns_error",
        "transport_error",
    } or clean.startswith(("http_401", "http_403", "http_407", "http_408", "http_425", "http_429")):
        return "not_verified", f"sitemap_source_{clean}"
    if clean.startswith(("http_404", "http_410", "http_5")) or clean in {
        "redirect_loop",
        "invalid_xml",
        "invalid_sitemap",
        "response_too_large",
    }:
        return "fail", f"sitemap_source_{clean}"
    return "not_verified", f"sitemap_source_failure_{clean}"


def build_sitemap_source_evidence(diagnostics: Any) -> list[dict[str, Any]]:
    """Project sitemap diagnostics without inventing missing provenance.

    Current discovery diagnostics identify roots individually but aggregate some
    child failure reasons. A failed source with no attached failure reason stays
    ``not_verified`` rather than being promoted to a site defect. If the shared
    producer later attaches an exact source-level reason, the conservative map
    above can classify known unusable files while access-limited failures remain
    unknown.
    """
    if not isinstance(diagnostics, dict):
        return []
    output: list[dict[str, Any]] = []
    for source in diagnostics.get("sitemap_sources") or []:
        if not isinstance(source, dict):
            continue
        url = _clean(source.get("url"))
        source_kind = _clean(source.get("source"), 120)
        outcome = _clean(source.get("outcome"), 120)
        source_reason = _clean(source.get("reason"), 160)
        loc_count = max(0, int(source.get("loc_count") or 0))
        if outcome == "urls":
            state, reason = "pass", "sitemap_source_retrieved"
        elif outcome == "failed":
            state, reason = _source_failure_state(source_reason)
        elif outcome == "empty":
            state, reason = "not_verified", "sitemap_source_empty_or_no_relevant_urls"
        else:
            state, reason = "not_verified", "sitemap_source_outcome_unknown"
        row = {
            "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
            "rule": "sitemap_source_integrity",
            "source_url": url,
            "source_kind": source_kind,
            "state": state,
            "reason": reason,
            "loc_count": loc_count,
        }
        if source_reason:
            row["source_reason"] = source_reason
        output.append(row)

    failure_buckets = diagnostics.get("sitemap_failure_reason_buckets") or {}
    if isinstance(failure_buckets, dict) and failure_buckets:
        output.append({
            "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
            "rule": "sitemap_retrieval_coverage",
            "state": "not_verified",
            "reason": "one_or_more_sitemap_retrieval_failures",
            "failure_reason_buckets": {
                _clean(key, 120): max(0, int(value or 0))
                for key, value in sorted(failure_buckets.items())
                if _clean(key, 120)
            },
            "deadline_exhausted": bool(diagnostics.get("sitemap_budget_exhausted")),
            "fetch_limit_reached": bool(diagnostics.get("sitemap_fetch_limit_reached")),
        })
    return output


def sitemap_coverage_from_scheduler(summary: Any, *, registration: Any = None) -> dict[str, Any]:
    registration = registration if isinstance(registration, dict) else {}
    candidate_universe_truncated = bool(registration.get("truncated"))
    eligible_unsampled = max(0, int(registration.get("eligible_unsampled") or 0))
    if not isinstance(summary, dict):
        return {
            "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
            "state": "not_verified",
            "reason": "scheduler_summary_unavailable",
            "eligible": 0,
            "eligible_unsampled": eligible_unsampled,
            "candidate_universe_truncated": candidate_universe_truncated,
            "completed": 0,
            "exhausted": 0,
        }
    stats = (summary.get("purposes") or {}).get("sitemap_target") or {}
    budget = summary.get("request_budget") or {}
    eligible = max(0, int(stats.get("eligible") or 0))
    completed = max(0, int(stats.get("completed") or 0))
    skipped = max(0, int(stats.get("skipped") or 0))
    exhausted = max(0, int(stats.get("exhausted") or 0))
    not_verified = max(0, int(stats.get("not_verified") or 0))
    if candidate_universe_truncated:
        state, reason = "not_verified", "candidate_universe_truncated"
    elif exhausted or budget.get("budget_exhausted") or budget.get("deadline_exhausted"):
        state, reason = "not_verified", "shared_probe_budget_or_deadline_exhausted"
    elif eligible and completed + skipped < eligible:
        state, reason = "not_verified", "eligible_sitemap_targets_not_fully_checked"
    elif not_verified:
        state, reason = "not_verified", "one_or_more_sitemap_targets_unverified"
    else:
        state, reason = "pass", "declared_sitemap_target_probe_coverage_completed"
    return {
        "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
        "state": state,
        "reason": reason,
        "eligible": eligible,
        "eligible_unsampled": eligible_unsampled,
        "candidate_universe_truncated": candidate_universe_truncated,
        "attempted": max(0, int(stats.get("attempted") or 0)),
        "completed": completed,
        "not_verified": not_verified,
        "skipped": skipped,
        "exhausted": exhausted,
    }
