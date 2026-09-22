import app.semantic_graph_evidence_cluster_flow_bound as binding


def graph():
    return {
        "version": "semantic_graph_evidence_v1",
        "scope": "observed_assessed_pages_only",
        "sitewide_orphan_claim": False,
        "nodes": [
            {"url": "https://e.test/a", "observed_in_edge_count": 1, "observed_out_edge_count": 1, "weighted_in": 0.5, "weighted_out": 0.7, "sitewide_orphan_claim": False},
            {"url": "https://e.test/b", "observed_in_edge_count": 1, "observed_out_edge_count": 1, "weighted_in": 0.7, "weighted_out": 0.5, "sitewide_orphan_claim": False},
        ],
        "edges": [
            {"source_url": "https://e.test/a", "target_url": "https://e.test/b", "observed_occurrences": 1, "strongest_zone": "contextual", "zone_confidence": 1.0, "weight": 0.7, "anchor_terms": []},
            {"source_url": "https://e.test/b", "target_url": "https://e.test/a", "observed_occurrences": 1, "strongest_zone": "navigation", "zone_confidence": 1.0, "weight": 0.5, "anchor_terms": []},
        ],
        "skipped_external_links": 0,
        "skipped_unassessed_targets": 0,
    }


def profile():
    return {
        "version": "semantic_cluster_profile_v1_vector_bound",
        "scope": "observed_assessed_pages_only",
        "state": "verified",
        "cluster_count": 1,
        "profile_count": 1,
        "profiles": [{"cluster_id": "sem_a", "state": "verified", "page_count": 2, "urls": ["https://e.test/a", "https://e.test/b"], "representative_url": "https://e.test/a"}],
        "semantic_vector_coverage_state": "complete",
        "semantic_pair_population_complete": True,
        "sitewide_semantic_coverage_claim": False,
        "customer_fix_created": False,
    }


def base(state="verified", reason="validated"):
    return {
        "version": "semantic_graph_evidence_v14_cluster_context_opportunity_bound",
        "state": state,
        "reason": reason,
        "graph": graph(),
        "semantic_cluster_profile": profile(),
        "sitewide_semantic_coverage_claim": False,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def test_v15_composes_cluster_flow_without_new_semantic_work(monkeypatch):
    calls = []

    def fake_builder(*args, **kwargs):
        calls.append((args, kwargs))
        return base()

    monkeypatch.setattr(binding, "build_cluster_context_bound_semantic_graph_evidence", fake_builder)
    result = binding.build_cluster_flow_bound_semantic_graph_evidence([], [], vectorizer=object())
    assert len(calls) == 1
    assert result["version"] == "semantic_graph_evidence_v15_semantic_cluster_link_flow_bound"
    assert result["previous_graph_envelope_version"] == "semantic_graph_evidence_v14_cluster_context_opportunity_bound"
    assert result["semantic_cluster_link_flow"]["state"] == "flow_observed"
    assert result["semantic_cluster_link_flow"]["clustered_endpoint_edge_count"] == 2
    assert result["customer_fix_created"] is False


def test_v15_fails_closed_when_cluster_flow_integrity_fails(monkeypatch):
    broken = base()
    broken["graph"]["nodes"][0]["weighted_out"] = 99.0
    monkeypatch.setattr(binding, "build_cluster_context_bound_semantic_graph_evidence", lambda *a, **k: broken)
    result = binding.build_cluster_flow_bound_semantic_graph_evidence([], [])
    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_weighted_out_mismatch"
    assert result["semantic_cluster_link_flow"]["state"] == "not_verified"


def test_v15_preserves_existing_v14_failure_reason(monkeypatch):
    prior = base(state="not_verified", reason="upstream_vector_integrity_failed")
    monkeypatch.setattr(binding, "build_cluster_context_bound_semantic_graph_evidence", lambda *a, **k: prior)
    result = binding.build_cluster_flow_bound_semantic_graph_evidence([], [])
    assert result["state"] == "not_verified"
    assert result["reason"] == "upstream_vector_integrity_failed"
    assert result["semantic_cluster_link_flow"]["state"] == "flow_observed"
