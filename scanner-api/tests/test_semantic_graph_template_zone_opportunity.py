from copy import deepcopy

from app.semantic_graph import ZONE_WEIGHTS
from app.semantic_graph_template_zone_opportunity import (
    RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
    raw_zone_template_contextual_internal_link_opportunities,
)


def zone_counts(**overrides):
    counts = {zone: 0 for zone in ZONE_WEIGHTS}
    counts.update(overrides)
    return counts


def template_contextual(*, observed_flow_present=True):
    return {
        "version": "template_contextual_internal_link_opportunity_v1_graph_bound",
        "scope": "observed_assessed_pages_only",
        "state": "candidate",
        "reason": "validated",
        "template_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "contextual_opportunity_integrity_state": "verified",
        "candidate_count": 1,
        "candidates_truncated": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "customer_fix_created": False,
        "candidates": [
            {
                "source_url": "https://e.test/products/a",
                "target_url": "https://e.test/guides/b",
                "source_group_id": "tmpl_products",
                "target_group_id": "tmpl_guides",
                "cross_template": True,
                "observed_template_flow_present": observed_flow_present,
                "sitewide_template_flow_claim": False,
            }
        ],
    }


def template_zone_flow():
    return {
        "version": "template_link_zone_flow_evidence_v2_raw_observation_bound",
        "scope": "observed_assessed_pages_only",
        "state": "verified",
        "reason": "validated",
        "template_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "raw_link_observation_integrity_state": "verified",
        "observed_template_flow_count": 1,
        "observed_directed_edge_count": 1,
        "observed_link_occurrence_count": 3,
        "flows": [
            {
                "source_group_id": "tmpl_products",
                "target_group_id": "tmpl_guides",
                "cross_template": True,
                "observed_link_occurrence_count": 3,
                "observed_directed_edge_count": 1,
                "observed_source_page_count": 1,
                "observed_target_page_count": 1,
                "contextual_occurrence_count": 1,
                "contextual_directed_edge_count": 1,
                "mixed_zone_directed_edge_count": 1,
                "zone_occurrence_counts": zone_counts(contextual=1, navigation=2),
                "strongest_zone_directed_edge_counts": zone_counts(contextual=1),
                "evidence_scope": "observed_assessed_pages_only",
                "sitewide_template_flow_claim": False,
                "sitewide_link_distribution_claim": False,
                "sitewide_link_absence_claim": False,
            }
        ],
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }


def empty_template_zone_flow():
    return {
        "version": "template_link_zone_flow_evidence_v2_raw_observation_bound",
        "scope": "observed_assessed_pages_only",
        "state": "verified",
        "reason": "validated",
        "template_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "raw_link_observation_integrity_state": "verified",
        "observed_template_flow_count": 0,
        "observed_directed_edge_count": 0,
        "observed_link_occurrence_count": 0,
        "flows": [],
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }


def test_raw_zone_binding_enriches_candidate_with_occurrence_and_mixed_zone_evidence():
    result = raw_zone_template_contextual_internal_link_opportunities(
        template_contextual(),
        template_zone_flow(),
    )

    assert result["version"] == RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION
    assert result["state"] == "candidate"
    row = result["candidates"][0]
    assert row["raw_zone_template_flow_present"] is True
    assert row["raw_zone_template_flow_link_occurrence_count"] == 3
    assert row["raw_zone_template_flow_directed_edge_count"] == 1
    assert row["raw_zone_template_flow_contextual_occurrence_count"] == 1
    assert row["raw_zone_template_flow_contextual_directed_edge_count"] == 1
    assert row["raw_zone_template_flow_mixed_zone_directed_edge_count"] == 1
    assert row["raw_zone_template_flow_zone_occurrence_counts"]["navigation"] == 2
    assert row["raw_zone_template_flow_evidence_state"] == "observed_in_assessed_sample"
    assert result["sitewide_link_absence_claim"] is False
    assert result["sitewide_template_flow_claim"] is False
    assert result["sitewide_link_distribution_claim"] is False
    assert result["customer_fix_created"] is False


def test_raw_zone_binding_preserves_no_observed_template_flow_as_sample_scoped_zero_evidence():
    result = raw_zone_template_contextual_internal_link_opportunities(
        template_contextual(observed_flow_present=False),
        empty_template_zone_flow(),
    )

    row = result["candidates"][0]
    assert row["raw_zone_template_flow_present"] is False
    assert row["raw_zone_template_flow_link_occurrence_count"] == 0
    assert row["raw_zone_template_flow_directed_edge_count"] == 0
    assert row["raw_zone_template_flow_contextual_occurrence_count"] == 0
    assert row["raw_zone_template_flow_zone_occurrence_counts"] == zone_counts()
    assert row["raw_zone_template_flow_evidence_state"] == "no_observed_flow_in_assessed_sample"
    assert result["sitewide_link_absence_claim"] is False


def test_raw_zone_binding_rejects_template_opportunity_version_mismatch():
    contextual = template_contextual()
    contextual["version"] = "forged"
    result = raw_zone_template_contextual_internal_link_opportunities(
        contextual,
        template_zone_flow(),
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "template_contextual_opportunity_version_mismatch"


def test_raw_zone_binding_rejects_unverified_raw_link_flow():
    flow = template_zone_flow()
    flow["raw_link_observation_integrity_state"] = "not_verified"
    result = raw_zone_template_contextual_internal_link_opportunities(
        template_contextual(),
        flow,
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "template_zone_flow_raw_link_not_verified"
    assert result["template_contextual_opportunity_integrity_state"] == "verified"


def test_raw_zone_binding_rejects_duplicate_template_flow_identity():
    flow = template_zone_flow()
    flow["flows"].append(deepcopy(flow["flows"][0]))
    flow["observed_template_flow_count"] = 2
    flow["observed_directed_edge_count"] = 2
    flow["observed_link_occurrence_count"] = 6
    result = raw_zone_template_contextual_internal_link_opportunities(
        template_contextual(),
        flow,
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "template_zone_flow_identity_invalid"


def test_raw_zone_binding_rejects_zone_occurrence_count_divergence():
    flow = template_zone_flow()
    flow["flows"][0]["zone_occurrence_counts"]["navigation"] = 1
    result = raw_zone_template_contextual_internal_link_opportunities(
        template_contextual(),
        flow,
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "template_zone_flow_occurrence_count_mismatch"


def test_raw_zone_binding_rejects_directed_edge_total_divergence():
    flow = template_zone_flow()
    flow["observed_directed_edge_count"] = 2
    result = raw_zone_template_contextual_internal_link_opportunities(
        template_contextual(),
        flow,
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "template_zone_flow_total_edge_count_mismatch"


def test_raw_zone_binding_rejects_candidate_vs_raw_flow_presence_divergence():
    result = raw_zone_template_contextual_internal_link_opportunities(
        template_contextual(observed_flow_present=False),
        template_zone_flow(),
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == "template_contextual_raw_zone_flow_presence_mismatch"
    assert result["template_contextual_opportunity_integrity_state"] == "verified"
    assert result["template_zone_flow_integrity_state"] == "verified"
