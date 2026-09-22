"""Pure, shadow-only replay trace for adaptive crawl selection.

The trace is engineering evidence only. It does not perform network I/O, schedule
pages, alter Standard 150, or authorize a production crawl budget.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .adaptive_crawl import (
    ADAPTIVE_SCORE_VERSION,
    MAX_ADAPTIVE_TARGET,
    STANDARD_150_TARGET,
    adaptive_candidate_score,
    select_adaptive_urls,
)

ADAPTIVE_SELECTION_TRACE_VERSION = "adaptive_selection_trace_v1"
ADAPTIVE_SELECTION_TRACE_INTEGRITY_VERSION = "adaptive_selection_trace_integrity_v1"


def _strict_discovered_urls(urls: Iterable[str]) -> list[str]:
    raw_urls = list(urls)
    for index, url in enumerate(raw_urls):
        if not isinstance(url, str):
            raise ValueError(f"discovered URL at index {index} must be a string")
        if not url or url != url.strip():
            raise ValueError(
                f"discovered URL at index {index} must be a non-empty exact identity "
                "without surrounding whitespace"
            )
    return raw_urls


def _ordered_unique(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _population_fingerprint(urls: Iterable[str]) -> str:
    payload = json.dumps(
        list(urls),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _coerce_target(target: Any) -> int:
    try:
        value = int(target or 0)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("target must be an integer-compatible value") from exc
    return max(0, min(value, MAX_ADAPTIVE_TARGET))


def _score_shape(
    url: str,
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
) -> dict[str, Any]:
    family = str(family_of(url) or "unknown")
    path = str(path_of(url) or "/")
    return adaptive_candidate_score(
        url,
        family=family,
        path=path,
        covered_families=set(),
        covered_signatures=set(),
        covered_prefixes=set(),
        metadata=None,
    )


def build_adaptive_selection_trace(
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    target: int,
    *,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic replay trace for an already-discovered URL population.

    The first 150 slots are delegated to ``select_adaptive_urls`` unchanged. The
    trace only explains/replays later adaptive choices; it does not create a second
    selector or a second crawl path.
    """
    raw_urls = _strict_discovered_urls(urls)
    bounded_target = min(len(raw_urls), _coerce_target(target))
    metadata = metadata_by_url or {}

    selected = select_adaptive_urls(
        raw_urls,
        family_of,
        path_of,
        bounded_target,
        metadata_by_url=metadata,
    )
    baseline_target = min(STANDARD_150_TARGET, bounded_target)
    baseline_selected = select_adaptive_urls(
        raw_urls,
        family_of,
        path_of,
        baseline_target,
        metadata_by_url=metadata,
    )

    if selected[: len(baseline_selected)] != baseline_selected:
        raise RuntimeError("adaptive selection violated the unchanged Standard-150 prefix")

    ordered = _ordered_unique(raw_urls)
    original_position = {url: index for index, url in enumerate(ordered)}
    chosen = set(baseline_selected)
    covered_families = {family_of(url) for url in baseline_selected}
    covered_signatures: set[str] = set()
    covered_prefixes: set[str] = set()
    for url in baseline_selected:
        shape = _score_shape(url, family_of, path_of)
        covered_signatures.add(str(shape["route_signature"]))
        covered_prefixes.add(str(shape["path_prefix"]))

    steps: list[dict[str, Any]] = []
    for selected_position, chosen_url in enumerate(
        selected[len(baseline_selected) :],
        start=len(baseline_selected),
    ):
        candidates = [url for url in ordered if url not in chosen]
        ranked: list[tuple[float, int, str, str, str, str, dict[str, Any]]] = []
        for url in candidates:
            family = str(family_of(url) or "unknown")
            path = str(path_of(url) or "/")
            scored = adaptive_candidate_score(
                url,
                family=family,
                path=path,
                covered_families=covered_families,
                covered_signatures=covered_signatures,
                covered_prefixes=covered_prefixes,
                metadata=metadata.get(url),
            )
            ranked.append(
                (
                    -float(scored["score"]),
                    original_position[url],
                    url,
                    family,
                    str(scored["route_signature"]),
                    str(scored["path_prefix"]),
                    scored,
                )
            )
        ranked.sort(key=lambda item: item[:6])
        if not ranked or ranked[0][2] != chosen_url:
            raise RuntimeError("adaptive trace replay diverged from selector output")

        _, discovery_index, _, family, signature, prefix, scored = ranked[0]
        runner_up_score = -ranked[1][0] if len(ranked) > 1 else None
        score = float(scored["score"])
        score_gap = None if runner_up_score is None else round(score - runner_up_score, 6)
        tied_on_score = sum(
            1
            for candidate in ranked
            if math.isclose(-candidate[0], score, rel_tol=0.0, abs_tol=1e-12)
        )

        steps.append(
            {
                "selected_position": selected_position,
                "url": chosen_url,
                "discovery_index": discovery_index,
                "candidate_count_before": len(ranked),
                "score": score,
                "score_gap_to_runner_up": score_gap,
                "tied_on_score_count": tied_on_score,
                "reasons": tuple(scored["reasons"]),
                "family": family,
                "route_signature": signature,
                "path_prefix": prefix,
            }
        )
        chosen.add(chosen_url)
        covered_families.add(family)
        covered_signatures.add(signature)
        covered_prefixes.add(prefix)

    return {
        "version": ADAPTIVE_SELECTION_TRACE_VERSION,
        "score_version": ADAPTIVE_SCORE_VERSION,
        "requested_target": int(target or 0),
        "bounded_target": bounded_target,
        "discovered_input_count": len(raw_urls),
        "unique_discovered_count": len(ordered),
        "baseline_selected_count": len(baseline_selected),
        "adaptive_selected_count": len(steps),
        "selected_count": len(selected),
        "input_population_fingerprint": _population_fingerprint(raw_urls),
        "selected_population_fingerprint": _population_fingerprint(selected),
        "selected_urls": tuple(selected),
        "steps": tuple(steps),
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _canonical(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(item) for item in value)
    return value


def validate_adaptive_selection_trace(
    trace: Mapping[str, Any],
    urls: Iterable[str],
    family_of: Callable[[str], str],
    path_of: Callable[[str], str],
    target: int,
    *,
    metadata_by_url: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay the selector and fail closed on any transported trace drift."""
    errors: list[str] = []
    try:
        expected = build_adaptive_selection_trace(
            urls,
            family_of,
            path_of,
            target,
            metadata_by_url=metadata_by_url,
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        return {
            "version": ADAPTIVE_SELECTION_TRACE_INTEGRITY_VERSION,
            "valid": False,
            "errors": ("replay_input_invalid",),
            "detail": str(exc),
        }

    for key, expected_value in expected.items():
        if _canonical(trace.get(key)) != _canonical(expected_value):
            errors.append(f"{key}_mismatch")

    unexpected_authority = (
        trace.get("population_scope_complete") is not False
        or trace.get("production_budget_authorized") is not False
        or trace.get("site_fully_understood") is not False
    )
    if unexpected_authority:
        errors.append("forbidden_authority_claim")

    return {
        "version": ADAPTIVE_SELECTION_TRACE_INTEGRITY_VERSION,
        "valid": not errors,
        "errors": tuple(dict.fromkeys(errors)),
        "input_population_fingerprint": expected["input_population_fingerprint"],
        "selected_population_fingerprint": expected["selected_population_fingerprint"],
    }
