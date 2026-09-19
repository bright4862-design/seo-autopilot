from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from .security import safe_get_once


COVERAGE_PROBE_SCHEDULER_VERSION = "coverage_probe_scheduler_v1_shared_request_budget"
LINK_INTEGRITY_PROBE_VERSION = "link_integrity_probe_v1_unsampled_same_site"
SOFT_404_PROBE_VERSION = "soft_404_probe_v1_active_baseline"
MAX_PROBE_OBSERVATION_SAMPLES = 40
MAX_SOFT_404_FAMILY_PROBES = 3

_REQUEST_LIMITS = {
    "basic": 4,
    "quick": 6,
    "deep": 12,
    "advanced": 18,
}

_PURPOSE_VERSIONS = {
    "internal_link": LINK_INTEGRITY_PROBE_VERSION,
    "soft_404_baseline": SOFT_404_PROBE_VERSION,
}

_SOFT_404_MARKER_RE = re.compile(r"__fixlist-missing-[a-f0-9]{10,24}", re.I)
_SOFT_404_INTENT_PATTERNS = (
    ("http_404_marker", re.compile(r"(?:^|\W)404(?:\W|$)", re.I)),
    ("page_not_found", re.compile(r"\bpage\s+(?:not\s+found|introuvable|non\s+trouv[ée]e?|no\s+encontrada|nicht\s+gefunden)\b", re.I)),
    ("not_found", re.compile(r"\bnot\s+found\b", re.I)),
    ("does_not_exist", re.compile(r"\b(?:does\s+not|doesn't)\s+exist\b", re.I)),
    ("could_not_find", re.compile(r"\b(?:could\s+not|can't|cannot)\s+find\b", re.I)),
    ("page_gone", re.compile(r"\b(?:page|resource)\s+(?:is\s+)?gone\b", re.I)),
)


def coverage_probe_request_limit(scan_mode: str) -> int:
    return int(_REQUEST_LIMITS.get(str(scan_mode or "advanced").lower(), _REQUEST_LIMITS["advanced"]))


def coverage_probe_version(purpose: str) -> str:
    return _PURPOSE_VERSIONS.get(str(purpose or "").strip(), COVERAGE_PROBE_SCHEDULER_VERSION)


def _bounded_text_list(values: Any, limit: int = 8, width: int = 500) -> list[str]:
    out: list[str] = []
    for value in values if isinstance(values, (list, tuple)) else []:
        clean = str(value or "").strip()[:width]
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _bounded_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "synthetic",
        "probe_kind",
        "page_family",
        "representative_path",
        "ordinal",
        "scope_prefix",
    }
    out: dict[str, Any] = {}
    for key in allowed:
        if key not in value:
            continue
        item = value[key]
        if isinstance(item, bool):
            out[key] = item
        elif isinstance(item, int):
            out[key] = max(0, min(10_000, item))
        else:
            out[key] = str(item or "").strip()[:500]
    return out


def _evidence_ref(purpose: str, url: str, state: str, status_code: int) -> str:
    digest = hashlib.sha256(
        f"{purpose}\x1f{url}\x1f{state}\x1f{int(status_code or 0)}".encode("utf-8")
    ).hexdigest()[:24]
    return f"{coverage_probe_version(purpose)}:{digest}"


def _normalize_scope_prefix(value: str) -> str:
    raw = str(value or "/").strip()
    path = urlparse(raw).path if raw.startswith(("http://", "https://")) else raw
    path = "/" + path.strip("/") if path and path != "/" else "/"
    return path.rstrip("/") if path != "/" else "/"


def _path_within_prefix(path: str, prefix: str) -> bool:
    clean = "/" + str(path or "/").lstrip("/")
    base = _normalize_scope_prefix(prefix)
    return base == "/" or clean == base or clean.startswith(base + "/")


def _synthetic_soft_404_url(origin: str, parent_path: str, seed: str, observed_urls: set[str]) -> str:
    parent = "/" + str(parent_path or "/").strip("/") if str(parent_path or "/").strip("/") else "/"
    for attempt in range(6):
        digest = hashlib.sha256(f"{seed}|{attempt}".encode("utf-8")).hexdigest()[:14]
        segment = f"__fixlist-missing-{digest}"
        path = f"{parent.rstrip('/')}/{segment}" if parent != "/" else f"/{segment}"
        candidate = origin.rstrip("/") + path
        if candidate not in observed_urls:
            return candidate
    return ""


def build_soft_404_probe_candidates(
    origin: str,
    scope_prefix: str,
    pages: list[dict],
    *,
    max_per_family: int = MAX_SOFT_404_FAMILY_PROBES,
) -> list[dict[str, Any]]:
    """Return deterministic synthetic missing-path probes inside the verified scan scope.

    One scope-root probe is always proposed. Each observed page family contributes
    at most three parent-directory probes. The shared scheduler remains the final
    request bound; this function only declares eligible candidates and never fetches.
    """
    parsed = urlparse(str(origin or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []
    normalized_origin = f"{parsed.scheme.lower()}://{parsed.netloc}"
    prefix = _normalize_scope_prefix(scope_prefix)
    observed_urls = {
        str(page.get("url") or "").strip()
        for page in pages
        if isinstance(page, dict) and str(page.get("url") or "").strip()
    }
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def add(parent: str, *, kind: str, family: str = "", representative: str = "", ordinal: int = 0) -> None:
        if not _path_within_prefix(parent, prefix):
            parent = prefix
        seed = f"{normalized_origin}|{prefix}|{kind}|{family}|{representative}|{ordinal}"
        url = _synthetic_soft_404_url(normalized_origin, parent, seed, observed_urls | seen_urls)
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        candidates.append({
            "url": url,
            "metadata": {
                "synthetic": True,
                "probe_kind": kind,
                "page_family": family,
                "representative_path": representative,
                "ordinal": ordinal,
                "scope_prefix": prefix,
            },
        })

    add(prefix, kind="scope_root", representative=prefix, ordinal=0)

    by_family: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        if not isinstance(page, dict):
            continue
        status = int(page.get("status_code") or 0)
        if not 200 <= status < 300 or page.get("fetch_error"):
            continue
        path = str(page.get("path") or urlparse(str(page.get("url") or "")).path or "/")
        if not _path_within_prefix(path, prefix):
            continue
        family = str(page.get("page_template_family") or "unknown").strip() or "unknown"
        if path not in by_family[family]:
            by_family[family].append(path)

    limit = max(0, min(MAX_SOFT_404_FAMILY_PROBES, int(max_per_family or 0)))
    for family in sorted(by_family):
        for ordinal, representative in enumerate(sorted(by_family[family])[:limit], start=1):
            parent = representative.rsplit("/", 1)[0] or "/"
            add(parent, kind="path_family", family=family, representative=representative, ordinal=ordinal)
    return candidates


def _soft_404_text(page: dict) -> str:
    values = [
        str(page.get("title") or ""),
        str(page.get("h1") or ""),
        str(page.get("meta_description") or ""),
    ]
    text = " ".join(values).lower()
    text = _SOFT_404_MARKER_RE.sub(" ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^\wÀ-ÿ'-]+", " ", text)).strip()


def soft_404_intent_signals(page: dict) -> list[str]:
    text = _soft_404_text(page)
    if not text:
        return []
    return [label for label, pattern in _SOFT_404_INTENT_PATTERNS if pattern.search(text)]


def _soft_404_tokens(page: dict) -> set[str]:
    return {token for token in _soft_404_text(page).split() if len(token) > 1}


def _soft_404_signature(page: dict) -> str:
    normalized = _soft_404_text(page)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _complete_accepted_html(page: dict) -> bool:
    if not isinstance(page, dict):
        return False
    status = int(page.get("status_code") or 0)
    if not 200 <= status < 300 or page.get("fetch_error"):
        return False
    if int(page.get("redirect_hop_count") or 0) > 0:
        return False
    if str(page.get("page_evidence_class") or "") != "usable_html":
        return False
    if page.get("raw_html_truncated") is True:
        return False
    content_type = str(page.get("content_type") or "").lower()
    if content_type and "html" not in content_type:
        return False
    if str(page.get("access_block_kind") or "").strip().lower() in {"challenge", "block", "rate_limit"}:
        return False
    return True


def build_soft_404_baseline_record(page: dict, probe_url: str, metadata: Any = None) -> dict[str, Any]:
    """Classify one synthetic missing-path response without inventing a baseline."""
    status = int(page.get("status_code") or 0) if isinstance(page, dict) else 0
    access_kind = str(page.get("access_block_kind") or "").strip().lower() if isinstance(page, dict) else ""
    fetch_error = str(page.get("fetch_error") or "").strip() if isinstance(page, dict) else ""
    base = {
        "version": SOFT_404_PROBE_VERSION,
        "probe_url": str(probe_url or "")[:2_000],
        "synthetic": True,
        "provenance": "deterministic_nonexistent_path",
        "status_code": max(0, status),
        "metadata": _bounded_metadata(metadata),
        "intent_signals": [],
        "signature": "",
        "word_count": max(0, int(page.get("word_count") or 0)) if isinstance(page, dict) else 0,
    }
    if access_kind in {"challenge", "block", "rate_limit"} or status in {401, 403, 407, 408, 425, 429}:
        return {**base, "state": "not_verified", "reason": access_kind or f"http_{status}"}
    if status <= 0 or fetch_error:
        return {**base, "state": "not_verified", "reason": fetch_error or "request_unverified"}
    if status in {404, 410}:
        return {**base, "state": "pass", "reason": f"hard_missing_http_{status}"}
    if not _complete_accepted_html(page):
        return {**base, "state": "not_verified", "reason": str(page.get("page_evidence_class") or "incomplete_response")}

    intent = soft_404_intent_signals(page)
    signature = _soft_404_signature(page)
    candidate = {
        **base,
        "intent_signals": intent,
        "signature": signature,
    }
    if not intent or not signature:
        return {**candidate, "state": "not_verified", "reason": "missing_intent_not_established"}
    return {**candidate, "state": "fail", "reason": "http_200_missing_intent_baseline"}


def compare_page_to_soft_404_baselines(page: dict, baselines: Any) -> dict[str, Any]:
    """Compare accepted assessed HTML with confirmed synthetic error baselines.

    A positive result requires both a verified 200 missing-path baseline and
    missing-page intent on the assessed page. Similarity is corroborating
    evidence; it cannot turn a generic app shell or challenged response into a
    soft-404 finding.
    """
    base = {
        "version": SOFT_404_PROBE_VERSION,
        "state": "not_verified",
        "reason": "no_verified_soft_404_baseline",
        "synthetic_baseline": True,
        "provenance": "deterministic_nonexistent_path",
        "similarity": None,
        "baseline_probe_url": "",
        "intent_signals": [],
    }
    if not _complete_accepted_html(page):
        return {**base, "reason": "assessed_page_not_complete_accepted_html"}
    verified = [
        item for item in (baselines if isinstance(baselines, list) else [])
        if isinstance(item, dict)
        and item.get("version") == SOFT_404_PROBE_VERSION
        and item.get("state") == "fail"
        and item.get("reason") == "http_200_missing_intent_baseline"
        and item.get("intent_signals")
    ]
    if not verified:
        return base

    page_intent = soft_404_intent_signals(page)
    if not page_intent:
        return {**base, "state": "pass", "reason": "assessed_page_has_no_missing_intent"}
    page_tokens = _soft_404_tokens(page)
    if not page_tokens:
        return {**base, "reason": "assessed_page_signature_unavailable"}

    best = None
    for item in verified:
        baseline_text = str(item.get("signature_text") or "")
        if baseline_text:
            baseline_tokens = set(baseline_text.split())
        else:
            # Current baseline records intentionally avoid retaining response copy.
            # Reconstruct only from optional bounded signature_tokens supplied by
            # the orchestrator/tests; absent tokens keep the comparison unknown.
            baseline_tokens = {str(token) for token in item.get("signature_tokens", []) if str(token)}
        if not baseline_tokens:
            continue
        union = page_tokens | baseline_tokens
        similarity = len(page_tokens & baseline_tokens) / len(union) if union else 0.0
        if best is None or similarity > best[0]:
            best = (similarity, item)
    if best is None:
        return {**base, "reason": "baseline_similarity_evidence_unavailable", "intent_signals": page_intent}

    similarity, matched = best
    if similarity < 0.45 or int(page.get("word_count") or 0) > 300:
        return {
            **base,
            "state": "pass",
            "reason": "active_baseline_not_similar",
            "similarity": round(similarity, 4),
            "baseline_probe_url": str(matched.get("probe_url") or "")[:2_000],
            "intent_signals": page_intent,
        }
    return {
        **base,
        "state": "fail",
        "reason": "active_soft_404_baseline_match",
        "similarity": round(similarity, 4),
        "baseline_probe_url": str(matched.get("probe_url") or "")[:2_000],
        "intent_signals": page_intent,
    }


def soft_404_signature_tokens(page: dict) -> list[str]:
    """Bounded non-copy token evidence used only for deterministic comparison."""
    return sorted(_soft_404_tokens(page))[:80]


class SharedCoverageProbeScheduler:
    """One finite request pool for Stage-2 follow-up checks.

    Assessed-page crawling owns its existing page cap. Follow-up probes are
    separate evidence and can only spend the smaller of the declared probe
    allowance and the crawler's remaining finite frontier-request ceiling.
    Actual HTTP identities are cached so two purposes (or two redirect chains)
    do not spend the budget twice for the same request URL.
    """

    def __init__(
        self,
        *,
        max_probe_requests: int,
        shared_request_limit: int,
        initial_request_count: int,
        deadline: float,
    ) -> None:
        self.max_probe_requests = max(0, int(max_probe_requests or 0))
        self.shared_request_limit = max(0, int(shared_request_limit or 0))
        self.initial_request_count = max(0, int(initial_request_count or 0))
        self.deadline = float(deadline or 0.0)
        self.started_at = time.monotonic()
        self.requests_consumed = 0
        self.reused_requests = 0
        self.deadline_exhausted = False
        self.budget_exhausted = False
        self._response_cache: dict[str, Any] = {}
        self._candidates: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "eligible": 0,
                "selected": 0,
                "attempted": 0,
                "completed": 0,
                "passed": 0,
                "failed": 0,
                "not_verified": 0,
                "skipped": 0,
                "exhausted": 0,
            }
        )
        self._observations: list[dict[str, Any]] = []
        self._observation_count = 0

    def register(
        self,
        *,
        purpose: str,
        url: str,
        source_pages: Any = None,
        link_text_samples: Any = None,
        metadata: Any = None,
    ) -> None:
        purpose = str(purpose or "").strip()
        url = str(url or "").strip()
        if not purpose or not url:
            return
        existing = self._candidates[purpose].get(url)
        if existing is None:
            self._candidates[purpose][url] = {
                "url": url,
                "source_pages": _bounded_text_list(source_pages),
                "link_text_samples": _bounded_text_list(link_text_samples),
                "metadata": _bounded_metadata(metadata),
            }
            self._stats[purpose]["eligible"] += 1
            return
        existing["source_pages"] = _bounded_text_list(
            [*existing.get("source_pages", []), *_bounded_text_list(source_pages)]
        )
        existing["link_text_samples"] = _bounded_text_list(
            [*existing.get("link_text_samples", []), *_bounded_text_list(link_text_samples)]
        )
        if metadata:
            existing["metadata"] = {**existing.get("metadata", {}), **_bounded_metadata(metadata)}

    def candidates(self, purpose: str) -> list[dict[str, Any]]:
        rows = self._candidates.get(str(purpose or ""), {})
        return [dict(rows[url]) for url in sorted(rows)]

    def _request_capacity_available(self) -> bool:
        if self.deadline and time.monotonic() >= self.deadline:
            self.deadline_exhausted = True
            return False
        if self.requests_consumed >= self.max_probe_requests:
            self.budget_exhausted = True
            return False
        if self.initial_request_count + self.requests_consumed >= self.shared_request_limit:
            self.budget_exhausted = True
            return False
        return True

    def can_start_candidate(self, purpose: str, url: str) -> bool:
        del purpose
        if str(url or "") in self._response_cache:
            return True
        return self._request_capacity_available()

    def begin_candidate(self, purpose: str) -> None:
        stats = self._stats[str(purpose or "")]
        stats["selected"] += 1
        stats["attempted"] += 1

    async def fetch_once(self, client, url: str, *, max_decoded_bytes: int | None = None):
        request_url = str(url or "").strip()
        if request_url in self._response_cache:
            self.reused_requests += 1
            return self._response_cache[request_url]
        if not self._request_capacity_available():
            raise RuntimeError(
                "coverage_probe_deadline_exhausted"
                if self.deadline_exhausted
                else "coverage_probe_request_budget_exhausted"
            )
        # Spend the permit before I/O. A timeout/transport failure still consumed
        # a real outbound request and therefore still counts against the bound.
        self.requests_consumed += 1
        remaining = None if not self.deadline else self.deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            self.deadline_exhausted = True
            raise RuntimeError("coverage_probe_deadline_exhausted")
        try:
            request = safe_get_once(
                client,
                request_url,
                max_decoded_bytes=max_decoded_bytes,
            )
            response = (
                await request
                if remaining is None
                else await asyncio.wait_for(request, timeout=max(0.1, remaining))
            )
        except asyncio.TimeoutError as exc:
            self.deadline_exhausted = True
            raise RuntimeError("coverage_probe_deadline_exhausted") from exc
        if response is not None:
            self._response_cache[request_url] = response
        return response

    def record_exhausted(self, purpose: str, url: str, *, source_pages: Any = None, link_text_samples: Any = None, metadata: Any = None) -> None:
        purpose = str(purpose or "")
        self._stats[purpose]["exhausted"] += 1
        self._observations_append({
            "purpose": purpose,
            "version": coverage_probe_version(purpose),
            "state": "not_verified",
            "reason": "deadline_exhausted" if self.deadline_exhausted else "request_budget_exhausted",
            "observed_url": str(url or ""),
            "status_code": 0,
            "final_url": "",
            "source_pages": _bounded_text_list(source_pages),
            "link_text_samples": _bounded_text_list(link_text_samples),
            "metadata": _bounded_metadata(metadata),
        })

    def record_skipped(
        self,
        purpose: str,
        url: str,
        *,
        reason: str,
        source_pages: Any = None,
        link_text_samples: Any = None,
        metadata: Any = None,
    ) -> None:
        purpose = str(purpose or "")
        self._stats[purpose]["skipped"] += 1
        self._observations_append({
            "purpose": purpose,
            "version": coverage_probe_version(purpose),
            "state": "not_verified",
            "reason": str(reason or "")[:220],
            "observed_url": str(url or "")[:2_000],
            "status_code": 0,
            "final_url": "",
            "source_pages": _bounded_text_list(source_pages),
            "link_text_samples": _bounded_text_list(link_text_samples),
            "metadata": _bounded_metadata(metadata),
        })

    def record_result(
        self,
        purpose: str,
        url: str,
        *,
        state: str,
        reason: str,
        status_code: int = 0,
        final_url: str = "",
        source_pages: Any = None,
        link_text_samples: Any = None,
        metadata: Any = None,
    ) -> None:
        purpose = str(purpose or "")
        state = str(state or "not_verified")
        stats = self._stats[purpose]
        stats["completed"] += 1
        if state == "pass":
            stats["passed"] += 1
        elif state == "fail":
            stats["failed"] += 1
        elif state == "not_verified":
            stats["not_verified"] += 1
        else:
            stats["skipped"] += 1
        self._observations_append({
            "purpose": purpose,
            "version": coverage_probe_version(purpose),
            "state": state,
            "reason": str(reason or "")[:220],
            "observed_url": str(url or "")[:2_000],
            "status_code": max(0, int(status_code or 0)),
            "final_url": str(final_url or "")[:2_000],
            "source_pages": _bounded_text_list(source_pages),
            "link_text_samples": _bounded_text_list(link_text_samples),
            "metadata": _bounded_metadata(metadata),
        })

    def _observations_append(self, observation: dict[str, Any]) -> None:
        self._observation_count += 1
        if len(self._observations) >= MAX_PROBE_OBSERVATION_SAMPLES:
            return
        observation = dict(observation)
        observation["evidence_ref"] = _evidence_ref(
            observation.get("purpose", ""),
            observation.get("observed_url", ""),
            observation.get("state", ""),
            int(observation.get("status_code") or 0),
        )
        self._observations.append(observation)

    def summary(self) -> dict[str, Any]:
        remaining_probe = max(0, self.max_probe_requests - self.requests_consumed)
        remaining_shared = max(
            0,
            self.shared_request_limit - self.initial_request_count - self.requests_consumed,
        )
        return {
            "version": COVERAGE_PROBE_SCHEDULER_VERSION,
            "request_budget": {
                "configured_probe_requests": self.max_probe_requests,
                "shared_request_limit": self.shared_request_limit,
                "crawl_requests_consumed": self.initial_request_count,
                "requests_consumed": self.requests_consumed,
                "requests_reused": self.reused_requests,
                "requests_remaining": min(remaining_probe, remaining_shared),
                "budget_exhausted": self.budget_exhausted,
                "deadline_exhausted": self.deadline_exhausted,
                "time_budget_seconds": round(max(0.0, self.deadline - self.started_at), 3) if self.deadline else None,
            },
            "purposes": {
                purpose: dict(stats)
                for purpose, stats in sorted(self._stats.items())
            },
            "observations": list(self._observations),
            "observation_samples_truncated": self._observation_count > len(self._observations),
        }