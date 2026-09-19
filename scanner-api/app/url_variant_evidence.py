from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


URL_VARIANT_EVIDENCE_VERSION = "url_variant_probe_v1_bounded_exact_identity"
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


def _canonical_url(page: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return _clean(page.get("canonical_url") or page.get("canonical"))


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
    state = _clean(page.get("indexability_state"), 120).lower()
    robots = _clean(page.get("robots_indexability_status"), 120).lower()
    return robots == "noindex" or state == "noindex" or "noindex" in state


def _raw_url_parts(url: str) -> tuple[str, str, str]:
    """Return raw authority, path and query/fragment suffix without serialization.

    `urlsplit` is fine for scope validation, but its serializer can erase the
    distinction between `/page` and `/page?`. B16 evidence must retain that exact
    observed spelling, so path mutations splice the original string instead.
    """
    value = _clean(url)
    scheme_at = value.find("://")
    if scheme_at < 0:
        return "", "", ""
    authority_start = scheme_at + 3
    delimiter_positions = [
        pos for marker in ("/", "?", "#")
        if (pos := value.find(marker, authority_start)) >= 0
    ]
    first = min(delimiter_positions) if delimiter_positions else len(value)
    authority = value[:first]
    suffix_at = min(
        [pos for marker in ("?", "#") if (pos := value.find(marker, first)) >= 0]
        or [len(value)]
    )
    path = value[first:suffix_at] if first < suffix_at else ""
    suffix = value[suffix_at:]
    return authority, path, suffix


def _replace_path_preserving_suffix(url: str, path: str) -> str:
    authority, _, suffix = _raw_url_parts(url)
    if not authority:
        return ""
    clean_path = path if path.startswith("/") else "/" + path
    return f"{authority}{clean_path}{suffix}"


def _toggle_trailing_slash(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc or parsed.path in {"", "/"}:
        return ""
    path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path + "/"
    return _replace_path_preserving_suffix(url, path)


def _toggle_first_path_alpha_case(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path
    if not path:
        return ""
    chars = list(path)
    escape_remaining = 0
    for index, char in enumerate(chars):
        if escape_remaining:
            escape_remaining -= 1
            continue
        if char == "%" and index + 2 < len(chars):
            escape_remaining = 2
            continue
        if char.isalpha():
            chars[index] = char.upper() if char.islower() else char.lower()
            return _replace_path_preserving_suffix(url, "".join(chars))
    return ""


def _replace_origin(url: str, alias_origin: str) -> str:
    source = urlsplit(url)
    alias = urlsplit(alias_origin)
    if alias.scheme not in {"http", "https"} or not alias.netloc:
        return ""
    # Alias origins are caller-verified scope evidence. Preserve the source path
    # and raw query ordering; this branch does not infer aliases itself.
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
    """Build bounded variant candidates while preserving exact observed identity.

    Slash/case candidates are synthetic and explicitly labelled. Scheme or host
    aliases are generated only when the caller supplies a previously verified
    alias origin; this module never authorizes a sibling host. Meaningful query
    candidates must be supplied explicitly from observed/reviewed evidence, so
    arbitrary parameter mutations are never invented.

    Every returned row reports whether the candidate universe was truncated.
    That lets downstream coverage remain unknown instead of describing a bounded
    sample as exhaustive evidence.
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
        key = (source_url, probe_url, kind)
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "version": URL_VARIANT_EVIDENCE_VERSION,
            "source_url": source_url,
            "probe_url": probe_url,
            "kind": kind,
            "synthetic": bool(synthetic),
            "verified_alias": bool(verified_alias),
        })

    for source_url in sorted({_clean(value) for value in observed_urls if _clean(value)}):
        parsed = urlsplit(source_url)
        if _origin_key(source_url) != base_origin or not _path_within_scope(parsed.path, prefix):
            continue
        add(source_url, _toggle_trailing_slash(source_url), "slash", synthetic=True)
        add(source_url, _toggle_first_path_alpha_case(source_url), "case", synthetic=True)
        for alias in aliases:
            if alias != base_origin:
                add(
                    source_url,
                    _replace_origin(source_url, alias),
                    "verified_origin_alias",
                    synthetic=True,
                    verified_alias=True,
                )

    for item in meaningful_parameter_variants or []:
        if not isinstance(item, dict):
            continue
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

    eligible = len(rows)
    truncated = eligible > limit
    selected = rows[:limit]
    for row in selected:
        row["eligible_candidate_count"] = eligible
        row["candidate_universe_truncated"] = truncated
    return selected


def register_url_variant_candidates(scheduler, candidates: Iterable[dict[str, Any]], *, scope_prefix: str = "/") -> int:
    """Register candidates in the existing SharedCoverageProbeScheduler only."""
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
            metadata={
                "synthetic": bool(row.get("synthetic")),
                "probe_kind": kind,
                "representative_path": _clean(source_url, 500),
                "scope_prefix": _scope_prefix(scope_prefix),
            },
        )
        registered += 1
    return registered


def _unknown_reason(page: Any) -> str:
    if not isinstance(page, dict):
        return "response_unverified"
    status = _status(page)
    access_kind = _access_kind(page)
    if access_kind in {"challenge", "block", "rate_limit"} or status in _ACCESS_LIMIT_STATUSES:
        return access_kind or f"http_{status}"
    if status <= 0 or _fetch_error(page):
        return _fetch_error(page) or "request_unverified"
    return ""


def classify_url_variant(source_page: Any, variant_page: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    """Classify a pair without turning a synthetic probe into published proof.

    Redirect destination meaning belongs to B08. A synthetic probe may show that
    a candidate normalizes to the assessed source, but ``published_redirect_claim``
    remains false by construction. An independently live route is evidence that
    a variant exists, not proof that it duplicates the source; without canonical,
    redirect or separate content-equivalence evidence it therefore stays unknown.
    """
    source_url = _clean(candidate.get("source_url"))
    probe_url = _clean(candidate.get("probe_url"))
    kind = _clean(candidate.get("kind"), 120)
    base = {
        "version": URL_VARIANT_EVIDENCE_VERSION,
        "rule": "url_variant",
        "source_url": source_url,
        "probe_url": probe_url,
        "variant_kind": kind,
        "synthetic": bool(candidate.get("synthetic")),
        "published_redirect_claim": False,
        "state": "not_verified",
        "reason": "response_unverified",
        "source_final_url": _final_url(source_page),
        "variant_final_url": _final_url(variant_page),
    }

    source_unknown = _unknown_reason(source_page)
    if source_unknown:
        return {**base, "reason": f"source_{source_unknown}"}
    variant_unknown = _unknown_reason(variant_page)
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
        if variant_final in {source_final, source_url}:
            return {**base, "state": "pass", "reason": "harmless_normalization_to_source"}
        return {**base, "reason": "redirect_meaning_requires_b08"}

    canonical = _canonical_url(variant_page)
    if canonical and canonical in {source_url, source_final}:
        return {**base, "state": "pass", "reason": "variant_canonicalized_to_source"}
    if _is_noindex(variant_page):
        return {**base, "reason": "live_noindex_variant_requires_policy_judgment"}
    if probe_url != source_url and variant_final != source_final:
        return {**base, "reason": "distinct_live_variant_requires_equivalence_evidence"}
    return {**base, "state": "pass", "reason": "same_effective_route"}


def url_variant_coverage_from_scheduler(summary: Any, *, candidates: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    candidate_rows = [row for row in (candidates or []) if isinstance(row, dict)]
    candidate_universe_truncated = any(bool(row.get("candidate_universe_truncated")) for row in candidate_rows)
    eligible_candidate_count = max(
        [int(row.get("eligible_candidate_count") or 0) for row in candidate_rows] or [0]
    )
    if not isinstance(summary, dict):
        return {
            "version": URL_VARIANT_EVIDENCE_VERSION,
            "state": "not_verified",
            "reason": "scheduler_summary_unavailable",
            "eligible": 0,
            "eligible_candidate_count": eligible_candidate_count,
            "candidate_universe_truncated": candidate_universe_truncated,
            "completed": 0,
            "exhausted": 0,
        }
    stats = (summary.get("purposes") or {}).get("url_variant") or {}
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
        state, reason = "not_verified", "eligible_url_variants_not_fully_checked"
    elif not_verified:
        state, reason = "not_verified", "one_or_more_url_variants_unverified"
    else:
        state, reason = "pass", "declared_url_variant_probe_coverage_completed"
    return {
        "version": URL_VARIANT_EVIDENCE_VERSION,
        "state": state,
        "reason": reason,
        "eligible": eligible,
        "eligible_candidate_count": eligible_candidate_count,
        "candidate_universe_truncated": candidate_universe_truncated,
        "attempted": max(0, int(stats.get("attempted") or 0)),
        "completed": completed,
        "not_verified": not_verified,
        "skipped": skipped,
        "exhausted": exhausted,
    }
