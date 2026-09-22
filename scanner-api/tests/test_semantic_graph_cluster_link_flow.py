from copy import deepcopy

from app.semantic_graph_cluster_link_flow import (
    SEMANTIC_CLUSTER_LINK_FLOW_VERSION,
    semantic_cluster_link_flow,
)


def graph():
    return {
        "version": "semantic_graph_evidence_v1",
        "scope": "observed_assessed_pages_only",
        "sitewide_orphan_claim": False,
        "nodes": [
            {"url": "https://e.test/a", "observed_in_edge_count": 1, "observed_out_edge_count": 2, "weighted_in": 0.4, "weighted_out": 1.5, "sitewide_orphan_claim": False},
            {"url": "https://e.test/b", "observed_in_edge_count": 1, "observed_out_edge_count": 1, "weighted_in": 0.9, "weighted_out": 0.4, "sitewide_orphan_claim": False},
            {"url": "https://e.test/c", "observed_in_edge_count": 1, "observed_out_edge_count": 1, "weighted_in": 0.6, "weighted_out": 0.6, "sitewide_orphan_claim": False},
            {"url": "https://e.test/d", "observed_in_edge_count": 1, "observed_out_edge_count": 0, "weighted_in": 0.6, "weighted_out": 0.0, "sitewide_orphan_claim": False},
        ],
        "edges": [
            {"source_url": "https://e.test/a", "target_url": "https://e.test/b", "observed_occurrences": 2, "strongest_zone": "contextual", "zone_confidence": 0.9, "weight": 0.9, "anchor_terms": ["topic"]},
            {"source_url": "https://e.test/a", "target_url": "https://e.test/c", "observed_occurrences": 1, "strongest_zone": "navigation", "zone_confidence": 0.8, "weight": 0.6, "anchor_terms": ["c"]},
            {"source_url": "https://e.test/b", "target_url": "https://e.test/a", "observed_occurrences": 1, "strongest_zone": "listing", "zone_confidence": 0.7, "weight": 0.4, "anchor_terms": ["a"]},
            {"source_url": "https://e.test/c", "target_url": "https://e.test/d", "observed_occurrences": 3, "strongest_zone": "contextual", "zone_confidence": 0.8, "weight": 0.6, "anchor_terms": ["d"]},
        ],
        "skipped_external_links": 0,
        "skipped_unassessed_targets": 0,
    }


def profile():
    return {
        "version": "semantic_cluster_profile_v1_vector_bound",
        "scope": "observed_assessed_pages_only",
        "state": "verified",
        "cluster_count": 2,
        "profile_count": 2,
        "profiles": [
            {"cluster_id": "sem_alpha", "state": "verified", "page_count": 2, "urls": ["https://e.test/a", "https://e.test/b"], "representative_url": "https://e.test/a"},
            {"cluster_id": "sem_beta", "state": "verified", "page_count": 2, "urls": ["https://e.test/c", "https://e.test/d"], "representative_url": "https://e.test/c"},
        ],
        "semantic_vector_coverage_state": "complete",
        "semantic_pair_population_complete": True,
        "sitewide_semantic_coverage_claim": False,
        "customer_fix_created": False,
    }


def test_cluster_flow_collapses_intra_and_inter_cluster_weighted_edges():
    result = semantic_cluster_link_flow(graph(), profile())
    assert result["version"] == SEMANTIC_CLUSTER_LINK_FLOW_VERSION
    assert result["state"] == "flow_observed"
    assert result["clustered_endpoint_edge_count"] == 4
    assert result["intra_cluster_edge_count"] == 3
    assert result["inter_cluster_edge_count"] == 1
    by_pair = {(row["source_cluster_id"], row["target_cluster_id"]): row for row in result["cluster_flows"]}
    alpha = by_pair[("sem_alpha", "sem_alpha")]
    assert alpha["edge_count"] == 2
    assert alpha["occurrence_count"] == 3
    assert alpha["weighted_strength"] == 1.3
    assert alpha["occurrence_weighted_strength"] == 2.2
    assert alpha["strongest_zone_edge_counts"] == {"contextual": 1, "listing": 1}
    cross = by_pair[("sem_alpha", "sem_beta")]
    assert cross["relation"] == "inter_cluster"
    assert cross["weighted_strength"] == 0.6


def test_cluster_summaries_are_directional_and_sample_scoped():
    result = semantic_cluster_link_flow(graph(), profile())
    rows = {row["cluster_id"]: row for row in result["cluster_summaries"]}
    assert rows["sem_alpha"]["observed_internal_edge_count"] == 2
    assert rows["sem_alpha"]["observed_outbound_cross_cluster_edge_count"] == 1
    assert rows["sem_alpha"]["observed_outbound_target_cluster_count"] == 1
    assert rows["sem_beta"]["observed_inbound_cross_cluster_edge_count"] == 1
    assert rows["sem_beta"]["observed_inbound_source_cluster_count"] == 1
    assert rows["sem_beta"]["sitewide_orphan_claim"] is False
    assert result["sitewide_link_distribution_claim"] is False
    assert result["customer_fix_created"] is False


def test_unclustered_endpoint_edges_are_counted_without_fabricating_cluster_flow():
    evidence = profile()
    evidence["cluster_count"] = evidence["profile_count"] = 1
    evidence["profiles"] = evidence["profiles"][:1]
    result = semantic_cluster_link_flow(graph(), evidence)
    assert result["clustered_endpoint_edge_count"] == 2
    assert result["unclustered_endpoint_edge_count"] == 2
    assert all(row["source_cluster_id"] == "sem_alpha" for row in result["cluster_flows"])
    assert all(row["target_cluster_id"] == "sem_alpha" for row in result["cluster_flows"])


def test_no_clusters_is_verified_no_cluster_observed_not_clean_sitewide_claim():
    evidence = profile()
    evidence.update({"state": "no_cluster_observed", "cluster_count": 0, "profile_count": 0, "profiles": []})
    result = semantic_cluster_link_flow(graph(), evidence)
    assert result["state"] == "no_cluster_observed"
    assert result["graph_integrity_state"] == "verified"
    assert result["semantic_cluster_profile_integrity_state"] == "verified"
    assert result["cluster_flows"] == []
    assert result["unclustered_endpoint_edge_count"] == 4
    assert result["sitewide_semantic_coverage_claim"] is False


def test_valid_clusters_with_no_clustered_edges_are_explicit():
    g = graph()
    g["edges"] = []
    for node in g["nodes"]:
        node.update({"observed_in_edge_count": 0, "observed_out_edge_count": 0, "weighted_in": 0.0, "weighted_out": 0.0})
    result = semantic_cluster_link_flow(g, profile())
    assert result["state"] == "no_cluster_flow_observed"
    assert result["cluster_count"] == 2
    assert result["cluster_flows"] == []
    assert result["sitewide_link_absence_claim"] is False


def test_graph_node_metric_forgery_fails_closed():
    g = graph()
    g["nodes"][0]["weighted_out"] = 999.0
    result = semantic_cluster_link_flow(g, profile())
    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_weighted_out_mismatch"
    assert result["cluster_flows"] == []


def test_duplicate_graph_edge_fails_closed():
    g = graph()
    g["edges"].append(deepcopy(g["edges"][0]))
    result = semantic_cluster_link_flow(g, profile())
    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_invalid"


def test_cluster_member_outside_graph_fails_closed():
    evidence = profile()
    evidence["profiles"][0]["urls"][1] = "https://e.test/missing"
    result = semantic_cluster_link_flow(graph(), evidence)
    assert result["state"] == "not_verified"
    assert result["graph_integrity_state"] == "verified"
    assert result["reason"] == "semantic_cluster_profile_member_outside_graph"


def test_overlapping_cluster_membership_fails_closed():
    evidence = profile()
    evidence["profiles"][1]["urls"][0] = "https://e.test/a"
    result = semantic_cluster_link_flow(graph(), evidence)
    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_profile_member_overlap"


def test_partial_profile_with_one_verified_cluster_remains_descriptive():
    evidence = profile()
    evidence["state"] = "partial"
    evidence["profiles"][1]["state"] = "not_verified"
    evidence["profiles"][1]["representative_url"] = None
    result = semantic_cluster_link_flow(graph(), evidence)
    assert result["state"] == "flow_observed"
    assert result["semantic_cluster_profile_state"] == "partial"
    summaries = {row["cluster_id"]: row for row in result["cluster_summaries"]}
    assert summaries["sem_beta"]["profile_state"] == "not_verified"
    assert result["sitewide_semantic_coverage_claim"] is False


def test_flow_order_and_edge_samples_are_deterministic():
    first = semantic_cluster_link_flow(graph(), profile())
    g = graph()
    g["nodes"] = list(reversed(g["nodes"]))
    g["edges"] = list(reversed(g["edges"]))
    evidence = profile()
    evidence["profiles"] = list(reversed(evidence["profiles"]))
    second = semantic_cluster_link_flow(g, evidence)
    assert first == second


def test_strongest_edge_tie_breaks_by_source_then_target():
    g = {
        "version": "semantic_graph_evidence_v1",
        "scope": "observed_assessed_pages_only",
        "sitewide_orphan_claim": False,
        "nodes": [
            {"url": "https://e.test/a", "observed_in_edge_count": 0, "observed_out_edge_count": 1, "weighted_in": 0.0, "weighted_out": 0.5, "sitewide_orphan_claim": False},
            {"url": "https://e.test/b", "observed_in_edge_count": 0, "observed_out_edge_count": 1, "weighted_in": 0.0, "weighted_out": 0.5, "sitewide_orphan_claim": False},
            {"url": "https://e.test/c", "observed_in_edge_count": 1, "observed_out_edge_count": 0, "weighted_in": 0.5, "weighted_out": 0.0, "sitewide_orphan_claim": False},
            {"url": "https://e.test/d", "observed_in_edge_count": 1, "observed_out_edge_count": 0, "weighted_in": 0.5, "weighted_out": 0.0, "sitewide_orphan_claim": False},
        ],
        "edges": [
            {"source_url": "https://e.test/b", "target_url": "https://e.test/d", "observed_occurrences": 1, "strongest_zone": "contextual", "zone_confidence": 1.0, "weight": 0.5, "anchor_terms": []},
            {"source_url": "https://e.test/a", "target_url": "https://e.test/c", "observed_occurrences": 1, "strongest_zone": "navigation", "zone_confidence": 1.0, "weight": 0.5, "anchor_terms": []},
        ],
        "skipped_external_links": 0,
        "skipped_unassessed_targets": 0,
    }
    evidence = profile()
    evidence["profiles"][0]["urls"] = ["https://e.test/a", "https://e.test/b"]
    evidence["profiles"][0]["representative_url"] = "https://e.test/a"
    evidence["profiles"][1]["urls"] = ["https://e.test/c", "https://e.test/d"]
    evidence["profiles"][1]["representative_url"] = "https://e.test/c"
    result = semantic_cluster_link_flow(g, evidence)
    row = next(row for row in result["cluster_flows"] if row["relation"] == "inter_cluster")
    assert row["strongest_edge"]["source_url"] == "https://e.test/a"
    assert row["strongest_edge"]["target_url"] == "https://e.test/c"
