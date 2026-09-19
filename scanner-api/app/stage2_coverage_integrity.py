from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


SITEMAP_INTEGRITY_EVIDENCE_VERSION = "sitemap_integrity_probe_v1_shared_scheduler"
URL_VARIANT_EVIDENCE_VERSION = "url_variant_probe_v1_bounded_exact_identity"

_ACCESS_LIMIT_STATUSES = {401, 403, 407, 408, 425, 429}
_MISSING_STATUSES = {404, 410}
_TRACKING_QUERY_PREFIXES = (
    "utm_",
    "gclid=",
    "fbclid=",
    "msclkid=",
)


def _clean(value: Any, width: int = 2_000) -> str:
    return str(value or "").strip()[:width]


def _scope_prefix(value: str) -> str:
    raw = _clean(value) or "/"
    path = urlsplit(raw).path if raw.startswith(("http://", "https://")) else raw
    path = "/" + path.strip("/") if path and path != "/" else "/"
    return path.rstrip("/") if path != "/" else "/"


def _path_within_scope(path: str, prefix: str) -> bool:
    clean = "/" + str(path or "/").lstrip("/")
    base = _scope_prefix(prefix)
    return base == "/" or clean == base or clean.startswith(base + "/")


def _origin_key(url: str) -> str:
    parsed = urlsplit(_clean(url))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _same_origin(url: str, origin: str) -> bool:
    return bool(_origin_key(url)) and _origin_key(url) == _origin_key(origin)


def _page_url(page: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return _clean(page.get("url") or page.get("request_url") or page.get("requested_url"))


def _final_url(page: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return _clean(page.get("final_url") or page.get("url") or page.get("request_url"))


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


def _canonical_url(page: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return _clean(page.get("canonical_url") or page.get("canonical"))


def _candidate_metadata(kind: str, source_url: str, scope_prefix: str, *, synthetic: bool) -> dict[str, Any]:
    # Keep keys inside SharedCoverageProbeScheduler's existing bounded metadata
    # envelope. Feature-specific evidence is produced by this module, not by
    # changing scheduler internals or creating another request pool.
    return {
        "synthetic": bool(synthetic),
        "probe_kind": _clean(kind, 120),
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
    """Register unsampled same-origin sitemap targets in the shared scheduler.

    ``entries`` may contain URL strings or dictionaries with ``url`` plus an
    optional ``sitemap_url``/``source_url``. The helper only declares eligible
    probes. It never fetches, changes assessed pages, widens host scope or owns a
    second request budget.
    """
    assessed = {_clean(value) for value in assessed_urls if _clean(value)}
    base_origin = _origin_key(origin)
    prefix = _scope_prefix(scope_prefix)
    max_candidates = max(0, min(100, int(max_candidates or 0)))
    selected = 0
    skipped_assessed = 0
    skipped_scope = 0
    skipped_invalid = 0
    seen: set[str] = set()

    normalized: list[tuple[str, str]] = []
    for item in entries:
        if isinstance(item, dict):
            url = _clean(item.get("url"))
            source = _clean(item.get("sitemap_url") or item.get("source_url") or item.get("declared_source"))
        else:
            url = _clean(item)
            source = ""
        if url:
            normalized.append((url, source))

    for url, source in sorted(normalized, key=lambda row: (row[0], row[1])):
        if url in seen:
            continue
        seen.add(url)
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
        if selected >= max_candidates:
            break
        scheduler.register(
            purpose="sitemap_target",
            url=url,
            source_pages=[source] if source else [],
            metadata=_candidate_metadata("sitemap_target", source or url, prefix, synthetic=False),
        )
        selected += 1

    return {
        "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
        "origin": base_origin,
        "scope_prefix": prefix,
        "registered": selected,
        "skipped_assessed": skipped_assessed,
        "skipped_outside_scope": skipped_scope,
        "skipped_invalid": skipped_invalid,
        "assessed_page_count_unchanged": True,
    }


def classify_sitemap_target(
    page: Any,
    *,
    requested_url: str,
    sitemap_source: str = "",
) -> dict[str, Any]:
    """Classify one probed sitemap target without promoting unknown access states."""
    requested = _clean(requested_url)
    status = _status(page)
    access_kind = _access_kind(page)
    fetch_error = _fetch_error(page)
    final = _final_url(page)
    base = {
        "version": SITEMAP_INTEGRITY_EVIDENCE_VERSION,
        "rule": "sitemap_integrity",
        "requested_url": requested,
        "final_url": final,
        "sitemap_source": _clean(sitemap_source),
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


def _toggle_trailing_slash(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc or parsed.path in {"", "/"}:
        return ""
    path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path + "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def _toggle_first_path_alpha_case(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path
    if not path:
        return ""
    chars = list(path)
    in_escape = 0
    for idx, char in enumerate(chars):
        if in_escape:
            in_escape -= 1
            continue
        if char == "%" and idx + 2 < len(chars):
            in_escape = 2
            continue
        if char.isalpha():
            chars[idx] = char.upper() if char.islower() else char.lower()
            changed = "".join(chars)
            return urlunsplit((parsed.scheme, parsed.netloc, changed, parsed.query, parsed.fragment))
    return ""


def _replace_origin(url: str, alias_origin: str) -> str:
    source = urlsplit(url)
    alias = urlsplit(alias_origin)
    if alias.scheme not in {"http", "https"} or not alias.netloc:
        return ""
    return urlunsplit((alias.scheme, alias.netloc, source.path, source.query, source.fragment))


def build_url_variant_candidates(
    observed_urls: Iterable[str],
    *,
    origin: str,
    scope_prefix: str = "/",
    verified_alias_origins: Iterable[str] | None = None,
    meaningful_parameter_variants: Iterable[dict[str, Any]] | None = None,
    max_candidates: int = 12,
) -> list[dict[str, Any]]:
    """Build bounded exact-identity variant candidates without widening scope.

    Slash/case candidates are synthetic and labelled. Scheme or apex/www host
    variants are generated only for caller-supplied *verified* alias origins;
    this helper never assumes sibling hosts are authorized. Meaningful parameter
    variants must be supplied explicitly as observed/reviewed source→variant
    pairs, so arbitrary query mutation is never invented here.
    """
    base_origin = _origin_key(origin)
    prefix = _scope_prefix(scope_prefix)
    limit = max(0, min(100, int(max_candidates or 0)))
    aliases = sorted({_origin_key(value) for value in (verified_alias_origins or []) if _origin_key(value)})
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(source_url: str, probe_url: str, kind: str, *, synthetic: bool, verified_alias: bool = False) -> None:
        if not source_url or not probe_url or source_url == probe_url:
            return
        if len(rows) >= limit:
            return
        key = (source_url, probe_url, kind)
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "source_url": source_url,
            "probe_url": probe_url,
            "kind": kind,
            "synthetic": bool(synthetic),
            "verified_alias": bool(verified_alias),
            "version": URL_VARIANT_EVIDENCE_VERSION,
        })

    for source_url in sorted({_clean(value) for value in observed_urls if _clean(value)}):
        if len(rows) >= limit:
            break
        parsed = urlsplit(source_url)
        if _origin_key(source_url) != base_origin or not _path_within_scope(parsed.path, prefix):
            continue
        add(source_url, _toggle_trailing_slash(source_url), "slash", synthetic=True)
        add(source_url, _toggle_first_path_alpha_case(source_url), "case", synthetic=True)
        for alias in aliases:
            if alias == base_origin:
                continue
            add(source_url, _replace_origin(source_url, alias), "verified_origin_alias", synthetic=True, verified_alias=True)

    for item in meaningful_parameter_variants or []:
        if len(rows) >= limit or not isinstance(item, dict):
            break
        source_url = _clean(item.get("source_url"))
        probe_url = _clean(item.get("variant_url") or item.get("probe_url"))
        if not source_url or not probe_url:
            continue
        source_parsed = urlsplit(source_url)
        probe_parsed = urlsplit(probe_url)
        if _origin_key(source_url) != base_origin or _origin_key(probe_url) != base_origin:
            continue
        if not _path_within_scope(source_parsed.path, prefix) or not _path_within_scope(probe_parsed.path, prefix):
            continue
        add(source_url, probe_url, "meaningful_parameter", synthetic=False)

    return rows[:limit]


def register_url_variant_candidates(scheduler, candidates: Iterable[dict[str, Any]], *, scope_prefix: str = "/") -> int:
    registered = 0
    for row in candidates:
        if not isinstance(row, dict):
            continue
        probe_url = _clean(row.get("probe_url"))
        source_url = _clean(row.get("source_url"))
        kind = _clean(row.get("kind"), 120)
        if not probe_url or not source_url or not kind:
            continue
        scheduler.register(
            purpose="url_variant",
            url=probe_url,
            source_pages=[source_url],
            metadata=_candidate_metadata(kind, source_url, scope_prefix, synthetic=bool(row.get("synthetic"))),
        )
        registered += 1
    return registered


def _variant_unknown_reason(page: Any) -> str:
    if not isinstance(page, dict):
        return "response_unverified"
    status = _status(page)
    access_kind = _access_kind(page)
    if access_kind in {"challenge", "block", "rate_limit"} or status in _ACCESS_LIMIT_STATUSES:
        return access_kind or f"http_{status}"
    if status <= 0 or _fetch_error(page):
        return _fetch_error(page) or "request_unverified"
    return ""


def classify_url_variant(
    source_page: Any,
    variant_page: Any,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Classify a bounded variant observation while preserving exact identities.

    Synthetic probes can establish that a candidate normalizes or independently
    resolves, but they are never described as a published redirect. Redirect
    destination *meaning* remains B08's responsibility.
    """
    source_url = _clean(candidate.get("source_url"))
    probe_url = _clean(candidate.get("probe_url"))
    kind = _clean(candidate.get("kind"), 120)
    synthetic = bool(candidate.get("synthetic"))
    base = {
        "version": URL_VARIANT_EVIDENCE_VERSION,
        "rule": "url_variant",
        "source_url": source_url,
        "probe_url": probe_url,
        "variant_kind": kind,
        "synthetic": synthetic,
        "published_redirect_claim": False,
        "state": "not_verified",
        "reason": "response_unverified",
        "source_final_url": _final_url(source_page),
        "variant_final_url": _final_url(variant_page),
    }

    source_unknown = _variant_unknown_reason(source_page)
    if source_unknown:
        return {**base, "reason": f"source_{source_unknown}"}
    variant_unknown = _variant_unknown_reason(variant_page)
    if variant_unknown:
        return {**base, "reason": f"variant_{variant_unknown}"}

    variant_status = _status(variant_page)
    if variant_status in _MISSING_STATUSES:
        return {**base, "state": "pass", "reason": "variant_not_published"}
    if variant_status >= 500:
        return {**base, "reason": f"variant_http_{variant_status}"}
    if 300 <= variant_status < 400:
        return {**base, "reason": "redirect_meaning_requires_b08"}
    if not _complete_usable_html(source_page) or not _complete_usable_html(variant_page):
        return {**base, "reason": "complete_html_pair_unavailable"}

    source_final = _final_url(source_page) or source_url
    variant_final = _final_url(variant_page) or probe_url
    redirect_hops = int(variant_page.get("redirect_hop_count") or 0) if isinstance(variant_page, dict) else 0
    if redirect_hops > 0 or variant_final != probe_url:
        if variant_final == source_final or variant_final == source_url:
            return {**base, "state": "pass", "reason": "harmless_normalization_to_source"}
        return {**base, "reason": "redirect_meaning_requires_b08"}

    canonical = _canonical_url(variant_page)
    if canonical and canonical in {source_url, source_final}:
        return {**base, "state": "pass", "reason": "variant_canonicalized_to_source"}

    if probe_url != source_url and variant_final != source_final:
        return {**base, "state": "fail", "reason": "distinct_live_variant"}
    return {**base, "state": "pass", "reason": "same_effective_route"}


def feature_coverage_from_scheduler(summary: Any, purpose: str, *, version: str) -> dict[str, Any]:
    """Project scheduler diagnostics into a feature-owned truthful coverage record."""
    if not isinstance(summary, dict):
        return {
            "version": version,
            "state": "not_verified",
            "reason": "scheduler_summary_unavailable",
            "eligible": 0,
            "attempted": 0,
            "completed": 0,
            "exhausted": 0,
        }
    stats = (summary.get("purposes") or {}).get(purpose) or {}
    budget = summary.get("request_budget") or {}
    eligible = max(0, int(stats.get("eligible") or 0))
    attempted = max(0, int(stats.get("attempted") or 0))
    completed = max(0, int(stats.get("completed") or 0))
    exhausted = max(0, int(stats.get("exhausted") or 0))
    not_verified = max(0, int(stats.get("not_verified") or 0))
    skipped = max(0, int(stats.get("skipped") or 0))
    if exhausted or budget.get("budget_exhausted") or budget.get("deadline_exhausted"):
        state = "not_verified"
        reason = "shared_probe_budget_or_deadline_exhausted"
    elif eligible and completed + skipped < eligible:
        state = "not_verified"
        reason = "eligible_targets_not_fully_checked"
    elif not_verified:
        state = "not_verified"
        reason = "one_or_more_targets_unverified"
    else:
        state = "pass"
        reason = "declared_probe_coverage_completed"
    return {
        "version": version,
        "state": state,
        "reason": reason,
        "eligible": eligible,
        "attempted": attempted,
        "completed": completed,
        "not_verified": not_verified,
        "skipped": skipped,
        "exhausted": exhausted,
    }
