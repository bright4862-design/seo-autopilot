"""Pure next-generation semantic/site-graph evidence helpers.

This module performs no network I/O, writes no customer-facing Fixes, and does
not mutate scanner authority/persistence. It consumes already-observed page and
link evidence and emits bounded, versioned evidence that the serialized
integrator can later feed into root-cause/repair layers.

All absence statements are scoped to the observed sample. In particular, a
missing observed edge is never promoted into proof that a page is sitewide
orphaned or that a link is absent outside the assessed corpus.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from math import sqrt
import re
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlparse


GRAPH_EVIDENCE_VERSION = "semantic_graph_evidence_v1"
LINK_ZONE_VERSION = "link_zone_evidence_v1"
TEMPLATE_EVIDENCE_VERSION = "template_group_evidence_v1"
LOCAL_SEMANTIC_VERSION = "deterministic_local_semantic_v1"
NEAR_DUPLICATE_CANDIDATE_VERSION = "near_duplicate_candidate_v1"
CANNIBALIZATION_CANDIDATE_VERSION = "cannibalization_candidate_v1"
INTERNAL_LINK_OPPORTUNITY_VERSION = "internal_link_opportunity_v1"

MAX_PAGES = 1_000
MAX_LINKS = 50_000
MAX_LINKS_PER_SOURCE = 2_000
MAX_CANDIDATES = 250
MAX_SHARED_TERMS = 8
MAX_TEMPLATE_SAMPLES = 8
MAX_ANCHOR_TERMS = 12

ZONE_WEIGHTS = {
    "contextual": 1.00,
    "listing": 0.58,
    "aside": 0.42,
    "navigation": 0.34,
    "header": 0.26,
    "footer": 0.18,
    "facet": 0.08,
    "unknown": 0.22,
}

_TOKEN_RE = re.compile(r"[\w'-]{2,}", re.UNICODE)
_ID_SEGMENT = re.compile(r"^(?:\d{2,}|[0-9a-f]{8,}|[0-9a-f]{8}-[0-9a-f-]{27,})$", re.I)
_DATE_SEGMENT = re.compile(r"^(?:19|20)\d{2}$|^(?:0?[1-9]|1[0-2])$|^(?:0?[1-9]|[12]\d|3[01])$")
_FACET_TOKEN = re.compile(r"(?:filter|facet|sort|price|brand|size|color|colour|category|tag|page|view|availability)", re.I)
_LISTING_TOKEN = re.compile(r"(?:grid|listing|list|cards?|products?|results?|collection|catalog|archive)", re.I)
_CONTEXT_TOKEN = re.compile(r"(?:content|article|entry|post|prose|body|main)", re.I)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _url(value: Any) -> str:
    return _text(value)


def _tokens(value: Any) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(_text(value))]


def _usable_page(page: dict[str, Any]) -> bool:
    if not isinstance(page, dict):
        return False
    status = page.get("status_code")
    try:
        status_code = int(status or 0)
    except (TypeError, ValueError):
        return False
    evidence_class = page.get("page_evidence_class")
    if evidence_class is not None and evidence_class != "usable_html":
        return False
    return (
        200 <= status_code < 300
        and not page.get("fetch_error")
        and not page.get("raw_html_truncated")
    )


def _same_host(left: str, right: str) -> bool:
    try:
        return bool(left and right and urlparse(left).hostname and urlparse(left).hostname == urlparse(right).hostname)
    except Exception:
        return False


def _bounded_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(pages, list) or len(pages) > MAX_PAGES or any(not isinstance(page, dict) for page in pages):
        raise ValueError(f"Expected at most {MAX_PAGES} page dictionaries")
    return pages


def _bounded_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(links, list) or len(links) > MAX_LINKS or any(not isinstance(link, dict) for link in links):
        raise ValueError(f"Expected at most {MAX_LINKS} link observations")
    per_source: dict[str, int] = defaultdict(int)
    for link in links:
        source = _url(link.get("source_url") or link.get("source"))
        per_source[source] += 1
        if per_source[source] > MAX_LINKS_PER_SOURCE:
            raise ValueError("Link observations exceed per-source bound")
    return links


def infer_link_zone(link: dict[str, Any]) -> dict[str, Any]:
    """Classify one already-observed link using only local structural evidence.

    A false ``navigation_presence`` value is not sufficient to call a link
    contextual. Stronger DOM evidence is required; otherwise the result stays
    unknown. This prevents downstream logic from inventing contextual relevance.
    """
    if not isinstance(link, dict):
        raise ValueError("Expected link observation")

    tags = {str(value).strip().lower() for value in (link.get("ancestor_tags") or []) if str(value).strip()}
    roles = {str(value).strip().lower() for value in (link.get("ancestor_roles") or []) if str(value).strip()}
    tokens = " ".join(
        _text(value).lower()
        for value in (
            link.get("ancestor_classes"),
            link.get("ancestor_ids"),
            link.get("dom_path"),
            link.get("container_label"),
        )
        if value
    )
    source = _url(link.get("source_url") or link.get("source"))
    target = _url(link.get("target_url") or link.get("target") or link.get("href"))
    query_keys = {key.lower() for key, _ in parse_qsl(urlparse(target).query, keep_blank_values=True)} if target else set()
    anchor_tokens = set(_tokens(link.get("anchor_text") or link.get("text")))

    if "footer" in tags or "contentinfo" in roles:
        zone, confidence, reason = "footer", 0.99, "semantic_footer_ancestor"
    elif "nav" in tags or "navigation" in roles or link.get("navigation_presence") is True:
        zone, confidence, reason = "navigation", 0.96 if ("nav" in tags or "navigation" in roles) else 0.82, "semantic_navigation_evidence"
    elif "header" in tags or "banner" in roles:
        zone, confidence, reason = "header", 0.94, "semantic_header_ancestor"
    elif "aside" in tags or "complementary" in roles:
        zone, confidence, reason = "aside", 0.91, "semantic_aside_ancestor"
    elif query_keys and (any(_FACET_TOKEN.search(key) for key in query_keys) or _FACET_TOKEN.search(tokens)):
        zone, confidence, reason = "facet", 0.88, "query_or_container_facet_signal"
    elif _LISTING_TOKEN.search(tokens) or int(link.get("repeated_sibling_links") or 0) >= 3:
        zone, confidence, reason = "listing", 0.78, "repeated_listing_container_signal"
    elif "main" in tags or "article" in tags or "main" in roles or "article" in roles or _CONTEXT_TOKEN.search(tokens):
        zone, confidence, reason = "contextual", 0.86, "main_content_container_signal"
    else:
        zone, confidence, reason = "unknown", 0.0, "insufficient_structural_evidence"

    return {
        "version": LINK_ZONE_VERSION,
        "state": "observed_or_inferred" if zone != "unknown" else "not_verified",
        "zone": zone,
        "confidence": round(confidence, 4),
        "reason": reason,
        "source_url": source,
        "target_url": target,
        "anchor_terms": sorted(anchor_tokens)[:MAX_ANCHOR_TERMS],
    }


def _route_pattern(url: str) -> str:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return "/"
    pattern: list[str] = []
    for index, segment in enumerate(segments):
        clean = segment.lower()
        if _ID_SEGMENT.match(clean):
            pattern.append("{id}")
        elif index >= 1 and _DATE_SEGMENT.match(clean):
            pattern.append("{date}")
        elif index >= 1 and (len(clean) >= 14 or clean.count("-") >= 2):
            pattern.append("{slug}")
        else:
            pattern.append(clean)
    return "/" + "/".join(pattern)


def infer_template_groups(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Infer deterministic route/template groups without site-specific config."""
    pages = _bounded_pages(pages)
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    raw: list[tuple[dict[str, Any], str, str, str]] = []

    for page in pages:
        url = _url(page.get("url") or page.get("final_url") or page.get("page_url"))
        declared = _text(page.get("page_template_family"))
        if declared:
            key, state, reason = f"family:{declared.lower()}", "observed", "declared_page_template_family"
        elif url:
            key, state, reason = f"route:{_route_pattern(url)}", "inferred", "deterministic_route_pattern"
        else:
            key, state, reason = "unknown", "not_verified", "page_url_unavailable"
        counts[key] += 1
        raw.append((page, key, state, reason))

    for page, key, state, reason in raw:
        url = _url(page.get("url") or page.get("final_url") or page.get("page_url"))
        if state == "observed":
            confidence = 1.0
        elif state == "inferred" and counts[key] >= 2:
            confidence = 0.76
        elif state == "inferred":
            confidence = 0.42
        else:
            confidence = 0.0
        group_id = "tmpl_" + sha256(key.encode("utf-8")).hexdigest()[:12] if key != "unknown" else ""
        rows.append(
            {
                "url": url,
                "group_id": group_id,
                "template_key": key if key != "unknown" else None,
                "state": state,
                "confidence": round(confidence, 4),
                "reason": reason,
                "observed_group_size": counts[key] if key != "unknown" else 0,
            }
        )

    groups: list[dict[str, Any]] = []
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["group_id"]:
            by_group[row["group_id"]].append(row)
    for group_id in sorted(by_group):
        members = by_group[group_id]
        groups.append(
            {
                "group_id": group_id,
                "template_key": members[0]["template_key"],
                "page_count": len(members),
                "sample_urls": sorted(row["url"] for row in members if row["url"])[:MAX_TEMPLATE_SAMPLES],
                "sample_urls_truncated": len(members) > MAX_TEMPLATE_SAMPLES,
            }
        )

    return {
        "version": TEMPLATE_EVIDENCE_VERSION,
        "scope": "observed_assessed_pages_only",
        "pages": rows,
        "groups": groups,
    }


class SemanticVectorizer(Protocol):
    """Pluggable local interface. Implementations must return deterministic data."""

    version: str

    def vectors(self, pages: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        ...


class DeterministicLocalVectorizer:
    version = LOCAL_SEMANTIC_VERSION

    def vectors(self, pages: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        pages = _bounded_pages(pages)
        term_rows: dict[str, dict[str, float]] = {}
        document_frequency: dict[str, int] = defaultdict(int)
        for page in pages:
            url = _url(page.get("url") or page.get("final_url") or page.get("page_url"))
            if not url:
                continue
            weighted: dict[str, float] = defaultdict(float)
            sources = (
                (page.get("title"), 3.0),
                (page.get("h1"), 3.0),
                (" ".join(page.get("semantic_terms") or []) if isinstance(page.get("semantic_terms"), list) else "", 2.0),
                (urlparse(url).path.replace("-", " ").replace("_", " "), 1.0),
            )
            for value, weight in sources:
                for token in _tokens(value):
                    weighted[token] += weight
            if not weighted:
                continue
            term_rows[url] = dict(weighted)
            for token in weighted:
                document_frequency[token] += 1

        total_docs = max(1, len(term_rows))
        vectors: dict[str, dict[str, float]] = {}
        for url, terms in term_rows.items():
            vector: dict[str, float] = {}
            for token, tf in terms.items():
                idf = 1.0 + (total_docs / max(1, document_frequency[token])) ** 0.5
                vector[token] = round(tf * idf, 8)
            vectors[url] = vector
        return vectors


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in shared)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def semantic_similarity_matrix(
    pages: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    min_similarity: float = 0.0,
) -> dict[str, Any]:
    pages = _bounded_pages(pages)
    if not 0.0 <= float(min_similarity) <= 1.0:
        raise ValueError("min_similarity out of bounds")
    vectorizer = vectorizer or DeterministicLocalVectorizer()
    vectors = vectorizer.vectors(pages)
    urls = sorted(vectors)
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(urls):
        for right in urls[left_index + 1 :]:
            similarity = _cosine(vectors[left], vectors[right])
            if similarity + 1e-12 < min_similarity:
                continue
            shared = sorted(set(vectors[left]) & set(vectors[right]), key=lambda token: (-(vectors[left][token] + vectors[right][token]), token))
            pairs.append(
                {
                    "left_url": left,
                    "right_url": right,
                    "similarity": round(similarity, 6),
                    "shared_terms": shared[:MAX_SHARED_TERMS],
                }
            )
    pairs.sort(key=lambda row: (-row["similarity"], row["left_url"], row["right_url"]))
    return {
        "version": getattr(vectorizer, "version", "semantic_vectorizer_unknown"),
        "scope": "observed_assessed_pages_only",
        "vectorized_pages": len(vectors),
        "pairs": pairs[:MAX_CANDIDATES],
        "pairs_truncated": len(pairs) > MAX_CANDIDATES,
        "vectors": vectors,
    }


def semantic_clusters(
    pages: list[dict[str, Any]],
    *,
    threshold: float = 0.62,
    vectorizer: SemanticVectorizer | None = None,
) -> dict[str, Any]:
    if not 0.0 <= float(threshold) <= 1.0:
        raise ValueError("threshold out of bounds")
    matrix = semantic_similarity_matrix(pages, vectorizer=vectorizer, min_similarity=threshold)
    urls = sorted(matrix["vectors"])
    parent = {url: url for url in urls}

    def root(url: str) -> str:
        while parent[url] != url:
            parent[url] = parent[parent[url]]
            url = parent[url]
        return url

    for pair in matrix["pairs"]:
        left_root, right_root = root(pair["left_url"]), root(pair["right_url"])
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
        clusters.append(
            {
                "cluster_id": "sem_" + sha256("|".join(ordered).encode("utf-8")).hexdigest()[:12],
                "page_count": len(ordered),
                "urls": ordered,
            }
        )
    clusters.sort(key=lambda row: (-row["page_count"], row["cluster_id"]))
    return {
        "version": matrix["version"],
        "threshold": float(threshold),
        "scope": matrix["scope"],
        "clusters": clusters,
    }


def _b10_shingles(page: dict[str, Any]) -> frozenset[str]:
    if (
        page.get("main_text_verified") is not True
        or page.get("main_text_representation") != "sha256_5_token_shingles_v1"
    ):
        return frozenset()
    values = [token.lower() for token in _text(page.get("main_text")).split() if re.fullmatch(r"[0-9a-f]{16}", token.lower())]
    return frozenset(values)


def near_duplicate_candidates(
    pages: list[dict[str, Any]],
    *,
    threshold: float = 0.82,
) -> dict[str, Any]:
    pages = _bounded_pages(pages)
    if not 0.5 <= float(threshold) <= 1.0:
        raise ValueError("threshold out of bounds")
    rows = []
    for page in pages:
        url = _url(page.get("url") or page.get("final_url") or page.get("page_url"))
        shingles = _b10_shingles(page)
        if url and shingles:
            rows.append((url, shingles))
    candidates: list[dict[str, Any]] = []
    for index, (left_url, left_set) in enumerate(rows):
        for right_url, right_set in rows[index + 1 :]:
            union = left_set | right_set
            similarity = len(left_set & right_set) / len(union) if union else 0.0
            if similarity >= threshold:
                candidates.append(
                    {
                        "left_url": left_url,
                        "right_url": right_url,
                        "similarity": round(similarity, 6),
                        "evidence": "verified_b10_main_content_shingles",
                    }
                )
    candidates.sort(key=lambda row: (-row["similarity"], row["left_url"], row["right_url"]))
    return {
        "version": NEAR_DUPLICATE_CANDIDATE_VERSION,
        "scope": "observed_assessed_pages_only",
        "eligible_pages": len(rows),
        "state": "not_verified" if not rows else ("candidate" if candidates else "no_candidate_observed"),
        "candidates": candidates[:MAX_CANDIDATES],
        "candidates_truncated": len(candidates) > MAX_CANDIDATES,
    }


def _explicitly_indexable(page: dict[str, Any]) -> bool:
    if page.get("indexable") is True:
        return True
    if page.get("indexability_state") in {"indexable", "pass"}:
        return True
    return False


def cannibalization_candidates(
    pages: list[dict[str, Any]],
    *,
    semantic_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    vectorizer: SemanticVectorizer | None = None,
) -> dict[str, Any]:
    pages = _bounded_pages(pages)
    by_url = {
        _url(page.get("url") or page.get("final_url") or page.get("page_url")): page
        for page in pages
        if _url(page.get("url") or page.get("final_url") or page.get("page_url"))
    }
    semantic = semantic_similarity_matrix(pages, vectorizer=vectorizer, min_similarity=semantic_threshold)
    duplicate_pairs = {
        tuple(sorted((row["left_url"], row["right_url"])))
        for row in near_duplicate_candidates(pages, threshold=duplicate_threshold)["candidates"]
    }
    candidates: list[dict[str, Any]] = []
    for pair in semantic["pairs"]:
        left_url, right_url = pair["left_url"], pair["right_url"]
        left_page, right_page = by_url[left_url], by_url[right_url]
        if not (_usable_page(left_page) and _usable_page(right_page)):
            continue
        if not (_explicitly_indexable(left_page) and _explicitly_indexable(right_page)):
            continue
        if tuple(sorted((left_url, right_url))) in duplicate_pairs:
            continue
        candidates.append(
            {
                "left_url": left_url,
                "right_url": right_url,
                "semantic_similarity": pair["similarity"],
                "shared_terms": pair["shared_terms"],
                "near_duplicate_excluded": True,
                "indexability_verified": True,
                "state": "candidate",
                "reason": "distinct_indexable_pages_share_local_semantic_intent",
            }
        )
    candidates.sort(key=lambda row: (-row["semantic_similarity"], row["left_url"], row["right_url"]))
    return {
        "version": CANNIBALIZATION_CANDIDATE_VERSION,
        "scope": "observed_assessed_pages_only",
        "state": "candidate" if candidates else ("not_verified" if not semantic["vectorized_pages"] else "no_candidate_observed"),
        "candidates": candidates[:MAX_CANDIDATES],
        "candidates_truncated": len(candidates) > MAX_CANDIDATES,
    }


def build_weighted_internal_link_graph(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
) -> dict[str, Any]:
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    page_urls = {
        _url(page.get("url") or page.get("final_url") or page.get("page_url"))
        for page in pages
        if _url(page.get("url") or page.get("final_url") or page.get("page_url"))
    }
    node_rows = {
        url: {
            "url": url,
            "observed_in_edge_count": 0,
            "observed_out_edge_count": 0,
            "weighted_in": 0.0,
            "weighted_out": 0.0,
        }
        for url in sorted(page_urls)
    }
    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    skipped_external = 0
    skipped_unassessed = 0

    for link in links:
        source = _url(link.get("source_url") or link.get("source"))
        target = _url(link.get("target_url") or link.get("target") or link.get("href"))
        if not source or not target or source == target:
            continue
        if not _same_host(source, target):
            skipped_external += 1
            continue
        if source not in page_urls or target not in page_urls:
            skipped_unassessed += 1
            continue
        zone = infer_link_zone(link)
        base_weight = ZONE_WEIGHTS[zone["zone"]]
        anchor_bonus = min(0.08, 0.01 * len(zone["anchor_terms"]))
        confidence_multiplier = 0.5 + 0.5 * float(zone["confidence"])
        weight = round((base_weight + anchor_bonus) * confidence_multiplier, 6)
        key = (source, target)
        current = aggregate.get(key)
        if current is None:
            aggregate[key] = {
                "source_url": source,
                "target_url": target,
                "observed_occurrences": 1,
                "strongest_zone": zone["zone"],
                "zone_confidence": zone["confidence"],
                "weight": weight,
                "anchor_terms": list(zone["anchor_terms"]),
            }
        else:
            current["observed_occurrences"] += 1
            if weight > current["weight"]:
                current["strongest_zone"] = zone["zone"]
                current["zone_confidence"] = zone["confidence"]
                current["weight"] = weight
            current["anchor_terms"] = sorted(set(current["anchor_terms"]) | set(zone["anchor_terms"]))[:MAX_ANCHOR_TERMS]

    edges = [aggregate[key] for key in sorted(aggregate)]
    for edge in edges:
        source, target, weight = edge["source_url"], edge["target_url"], float(edge["weight"])
        node_rows[source]["observed_out_edge_count"] += 1
        node_rows[target]["observed_in_edge_count"] += 1
        node_rows[source]["weighted_out"] += weight
        node_rows[target]["weighted_in"] += weight

    nodes = []
    for url in sorted(node_rows):
        row = node_rows[url]
        row["weighted_in"] = round(row["weighted_in"], 6)
        row["weighted_out"] = round(row["weighted_out"], 6)
        row["sitewide_orphan_claim"] = False
        nodes.append(row)

    return {
        "version": GRAPH_EVIDENCE_VERSION,
        "scope": "observed_assessed_pages_only",
        "sitewide_orphan_claim": False,
        "nodes": nodes,
        "edges": edges,
        "skipped_external_links": skipped_external,
        "skipped_unassessed_targets": skipped_unassessed,
    }


def internal_link_opportunities(
    pages: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    semantic_threshold: float = 0.58,
    vectorizer: SemanticVectorizer | None = None,
) -> dict[str, Any]:
    pages = _bounded_pages(pages)
    if not isinstance(graph, dict) or graph.get("version") != GRAPH_EVIDENCE_VERSION:
        raise ValueError("Expected semantic graph evidence")
    if not 0.0 <= float(semantic_threshold) <= 1.0:
        raise ValueError("semantic_threshold out of bounds")

    by_url = {
        _url(page.get("url") or page.get("final_url") or page.get("page_url")): page
        for page in pages
        if _url(page.get("url") or page.get("final_url") or page.get("page_url"))
    }
    nodes = {row["url"]: row for row in graph.get("nodes", []) if isinstance(row, dict) and row.get("url")}
    observed_edges = {
        (row.get("source_url"), row.get("target_url"))
        for row in graph.get("edges", [])
        if isinstance(row, dict)
    }
    semantic = semantic_similarity_matrix(pages, vectorizer=vectorizer, min_similarity=semantic_threshold)
    vectors = semantic["vectors"]
    candidates: list[dict[str, Any]] = []

    for pair in semantic["pairs"]:
        left, right = pair["left_url"], pair["right_url"]
        for source, target in ((left, right), (right, left)):
            if (source, target) in observed_edges:
                continue
            source_page, target_page = by_url.get(source), by_url.get(target)
            if not source_page or not target_page or not _usable_page(source_page) or not _usable_page(target_page):
                continue
            if not _explicitly_indexable(target_page):
                continue
            source_node, target_node = nodes.get(source, {}), nodes.get(target, {})
            target_in = float(target_node.get("weighted_in") or 0.0)
            source_out = float(source_node.get("weighted_out") or 0.0)
            target_need = 1.0 / (1.0 + target_in)
            source_capacity = 1.0 / (1.0 + max(0.0, source_out - 3.0) / 8.0)
            score = 0.72 * pair["similarity"] + 0.20 * target_need + 0.08 * source_capacity
            shared = sorted(set(vectors.get(source, {})) & set(vectors.get(target, {})), key=lambda token: (-(vectors[source][token] + vectors[target][token]), token))
            candidates.append(
                {
                    "source_url": source,
                    "target_url": target,
                    "semantic_similarity": pair["similarity"],
                    "shared_terms": shared[:MAX_SHARED_TERMS],
                    "observed_edge_present": False,
                    "target_observed_weighted_in": round(target_in, 6),
                    "source_observed_weighted_out": round(source_out, 6),
                    "opportunity_score": round(score, 6),
                    "proposed_zone": "contextual",
                    "evidence_scope": "observed_assessed_pages_only",
                    "sitewide_link_absence_claim": False,
                    "state": "candidate",
                }
            )

    candidates.sort(key=lambda row: (-row["opportunity_score"], row["source_url"], row["target_url"]))
    return {
        "version": INTERNAL_LINK_OPPORTUNITY_VERSION,
        "scope": "observed_assessed_pages_only",
        "sitewide_link_absence_claim": False,
        "state": "candidate" if candidates else ("not_verified" if not semantic["vectorized_pages"] else "no_candidate_observed"),
        "candidates": candidates[:MAX_CANDIDATES],
        "candidates_truncated": len(candidates) > MAX_CANDIDATES,
    }


def build_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
) -> dict[str, Any]:
    """Build the complete Lane-B evidence envelope without customer decisions."""
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    graph = build_weighted_internal_link_graph(pages, links)
    templates = infer_template_groups(pages)
    clusters = semantic_clusters(pages, vectorizer=vectorizer)
    duplicates = near_duplicate_candidates(pages)
    cannibalization = cannibalization_candidates(pages, vectorizer=vectorizer)
    opportunities = internal_link_opportunities(pages, graph, vectorizer=vectorizer)
    return {
        "version": GRAPH_EVIDENCE_VERSION,
        "scope": "observed_assessed_pages_only",
        "sitewide_orphan_claim": False,
        "customer_fix_created": False,
        "template_evidence": templates,
        "graph": graph,
        "semantic_clusters": clusters,
        "near_duplicate_candidates": duplicates,
        "cannibalization_candidates": cannibalization,
        "internal_link_opportunities": opportunities,
    }
