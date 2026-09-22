"""Pure B10-bound near-duplicate cluster evidence for NextGen Lane B.

The helper consumes already-retained, verified main-content shingle evidence and
performs no network/model/provider work. It emits bounded descriptive evidence
only; it does not create customer Fixes, choose canonical pages, or make
sitewide duplication claims from an assessed sample.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import re
from typing import Any


NEAR_DUPLICATE_CLUSTER_VERSION = "near_duplicate_cluster_evidence_v1_b10_bound"
EVIDENCE_SCOPE = "observed_assessed_pages_only"
B10_REPRESENTATION = "sha256_5_token_shingles_v1"
MAX_PAGES = 1_000
MAX_CLUSTERS = 250
_HEX_SHINGLE_RE = re.compile(r"[0-9a-f]{16}", re.I)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _page_url(page: dict[str, Any]) -> str:
    return _text(page.get("url") or page.get("final_url") or page.get("page_url"))


def _verified_shingles(page: dict[str, Any]) -> frozenset[str]:
    if (
        page.get("main_text_verified") is not True
        or page.get("main_text_representation") != B10_REPRESENTATION
    ):
        return frozenset()
    tokens = _text(page.get("main_text")).split()
    return frozenset(
        token.lower()
        for token in tokens
        if _HEX_SHINGLE_RE.fullmatch(token)
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _cluster_id(urls: list[str]) -> str:
    return "ndc_" + sha256("|".join(urls).encode("utf-8")).hexdigest()[:12]


def _not_verified(
    reason: str,
    *,
    input_page_count: int,
    identified_page_count: int,
    eligible_page_count: int,
) -> dict[str, Any]:
    return {
        "version": NEAR_DUPLICATE_CLUSTER_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "threshold": None,
        "input_page_count": input_page_count,
        "identified_page_count": identified_page_count,
        "eligible_page_count": eligible_page_count,
        "unidentified_page_count": input_page_count - identified_page_count,
        "unverified_main_content_page_count": identified_page_count - eligible_page_count,
        "coverage_state": "not_verified",
        "pair_scan_complete": False,
        "qualifying_pair_count": 0,
        "cluster_count": 0,
        "clusters": [],
        "clusters_truncated": False,
        "sitewide_near_duplicate_claim": False,
        "sitewide_coverage_claim": False,
        "customer_fix_created": False,
    }


def near_duplicate_cluster_evidence(
    pages: list[dict[str, Any]],
    *,
    threshold: float = 0.82,
) -> dict[str, Any]:
    """Build deterministic connected-component clusters from verified B10 shingles.

    Cluster membership uses threshold-qualified Jaccard edges over verified
    accepted-main-content shingles. Connected components are intentionally
    reported as such: ``chaining_observed`` is true when a component contains a
    member pair below the threshold, so consumers cannot mistake transitive
    membership for all-pairs equivalence.
    """
    if not isinstance(pages, list) or len(pages) > MAX_PAGES:
        raise ValueError(f"Expected at most {MAX_PAGES} page dictionaries")
    if any(not isinstance(page, dict) for page in pages):
        raise ValueError("Expected page dictionaries")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("threshold out of bounds")
    threshold = float(threshold)
    if not 0.5 <= threshold <= 1.0:
        raise ValueError("threshold out of bounds")

    input_page_count = len(pages)
    rows: dict[str, frozenset[str]] = {}
    identified_page_count = 0
    duplicate_identity = False

    for page in pages:
        url = _page_url(page)
        if not url:
            continue
        identified_page_count += 1
        if url in rows:
            duplicate_identity = True
            continue
        shingles = _verified_shingles(page)
        if shingles:
            rows[url] = shingles
        else:
            # Reserve the identity so a second copy cannot masquerade as unique.
            rows[url] = frozenset()

    if duplicate_identity:
        eligible_page_count = sum(1 for shingles in rows.values() if shingles)
        return _not_verified(
            "duplicate_page_identity",
            input_page_count=input_page_count,
            identified_page_count=identified_page_count,
            eligible_page_count=eligible_page_count,
        )

    eligible = {url: shingles for url, shingles in rows.items() if shingles}
    eligible_page_count = len(eligible)
    if not eligible:
        return _not_verified(
            "no_verified_b10_main_content",
            input_page_count=input_page_count,
            identified_page_count=identified_page_count,
            eligible_page_count=0,
        )

    urls = sorted(eligible)
    parent = {url: url for url in urls}

    def root(url: str) -> str:
        while parent[url] != url:
            parent[url] = parent[parent[url]]
            url = parent[url]
        return url

    qualifying_pair_count = 0
    for index, left in enumerate(urls):
        for right in urls[index + 1 :]:
            similarity = _jaccard(eligible[left], eligible[right])
            if similarity + 1e-12 < threshold:
                continue
            qualifying_pair_count += 1
            left_root, right_root = root(left), root(right)
            if left_root != right_root:
                parent[right_root] = left_root

    grouped: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        grouped[root(url)].append(url)

    clusters: list[dict[str, Any]] = []
    for members in grouped.values():
        if len(members) < 2:
            continue
        ordered = sorted(members)
        similarities: list[float] = []
        similarity_sums = {url: 0.0 for url in ordered}
        similarity_counts = {url: 0 for url in ordered}
        weakest_pair: tuple[float, str, str] | None = None
        strongest_pair: tuple[float, str, str] | None = None

        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                similarity = _jaccard(eligible[left], eligible[right])
                similarities.append(similarity)
                similarity_sums[left] += similarity
                similarity_sums[right] += similarity
                similarity_counts[left] += 1
                similarity_counts[right] += 1
                row = (similarity, left, right)
                if weakest_pair is None or row < weakest_pair:
                    weakest_pair = row
                if (
                    strongest_pair is None
                    or similarity > strongest_pair[0]
                    or (
                        similarity == strongest_pair[0]
                        and (left, right) < (strongest_pair[1], strongest_pair[2])
                    )
                ):
                    strongest_pair = row

        mean_by_url = {
            url: similarity_sums[url] / similarity_counts[url]
            for url in ordered
            if similarity_counts[url]
        }
        representative_url = min(
            mean_by_url,
            key=lambda url: (-mean_by_url[url], url),
        )
        pair_mean = sum(similarities) / len(similarities)
        pair_min = min(similarities)
        pair_max = max(similarities)
        clusters.append(
            {
                "cluster_id": _cluster_id(ordered),
                "page_count": len(ordered),
                "urls": ordered,
                "representative_url": representative_url,
                "representative_mean_similarity": round(mean_by_url[representative_url], 6),
                "pair_similarity_min": round(pair_min, 6),
                "pair_similarity_mean": round(pair_mean, 6),
                "pair_similarity_max": round(pair_max, 6),
                "weakest_pair": {
                    "left_url": weakest_pair[1],
                    "right_url": weakest_pair[2],
                    "similarity": round(weakest_pair[0], 6),
                },
                "strongest_pair": {
                    "left_url": strongest_pair[1],
                    "right_url": strongest_pair[2],
                    "similarity": round(strongest_pair[0], 6),
                },
                "chaining_observed": pair_min + 1e-12 < threshold,
                "all_pairs_meet_threshold": pair_min + 1e-12 >= threshold,
                "state": "candidate",
                "reason": "verified_b10_main_content_connected_component",
            }
        )

    clusters.sort(key=lambda row: (-row["page_count"], row["cluster_id"]))
    full_cluster_count = len(clusters)
    selected = clusters[:MAX_CLUSTERS]
    unidentified_page_count = input_page_count - identified_page_count
    unverified_main_content_page_count = identified_page_count - eligible_page_count
    coverage_state = (
        "complete"
        if eligible_page_count == input_page_count and unidentified_page_count == 0
        else "partial"
    )

    return {
        "version": NEAR_DUPLICATE_CLUSTER_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "candidate" if selected else "no_candidate_observed",
        "reason": (
            "verified_b10_near_duplicate_clusters_observed"
            if selected
            else "no_near_duplicate_cluster_observed_in_verified_b10_sample"
        ),
        "threshold": threshold,
        "input_page_count": input_page_count,
        "identified_page_count": identified_page_count,
        "eligible_page_count": eligible_page_count,
        "unidentified_page_count": unidentified_page_count,
        "unverified_main_content_page_count": unverified_main_content_page_count,
        "coverage_state": coverage_state,
        "pair_scan_complete": True,
        "qualifying_pair_count": qualifying_pair_count,
        "cluster_count": full_cluster_count,
        "clusters": selected,
        "clusters_truncated": full_cluster_count > MAX_CLUSTERS,
        "sitewide_near_duplicate_claim": False,
        "sitewide_coverage_claim": False,
        "customer_fix_created": False,
    }
