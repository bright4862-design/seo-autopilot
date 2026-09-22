from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph, infer_template_groups
from app.semantic_graph_contextual import contextual_internal_link_opportunities
from app.semantic_graph_template_opportunity import (
    TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
    template_contextual_internal_link_opportunities,
)


def page(url, family):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
    }


def link(source, target, *, zone="navigation"):
    row = {
        "source_url": source,
        "target_url": target,
        "anchor_text": "shared topic",
    }
    if zone == "contextual":
        row["ancestor_tags"] = ["a", "main"]
    elif zone == "navigation":
        row["ancestor_tags"] = ["a", "nav"]
    elif zone == "footer":
        row["ancestor_tags"] = ["a", "footer"]
    return row


class StableVectorizer:
    version = "stable_template_opportunity_test_v1"

    def vectors(self, pages):
        return {row["url"]: {"shared": 1.0} for row in pages}


def build_inputs(*, with_edge=True, same_template=False):
    left = "https://e.test/articles/a"
    right = "https://e.test/products/a"
    pages = [
        page(left, "article"),
        page(right, "article" if same_template else "product"),
    ]
    links = [link(left, right)] if with_edge else []
    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, links)
    contextual = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.5,
        vectorizer=StableVectorizer(),
    )
    return pages, templates, graph, contextual


def candidate(result, source, target):
    return next(
        row
        for row in result["candidates"]
        if row["source_url"] == source and row["target_url"] == target
    )


def test_template_contextual_opportunity_binds_observed_template_flow_to_candidate():
    pages, templates, graph, contextual = build_inputs(with_edge=True)

    result = template_contextual_internal_link_opportunities(templates, graph, contextual)

    assert result["version"] == TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION
    assert result["state"] == "candidate"
    assert result["template_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "verified"
    assert result["contextual_opportunity_integrity_state"] == "verified"
    row = candidate(result, pages[0]["url"], pages[1]["url"])
    assert row["cross_template"] is True
    assert row["observed_edge_present"] is True
    assert row["existing_strongest_zone"] == "navigation"
    assert row["observed_template_flow_present"] is True
    assert row["observed_template_flow_directed_edge_count"] == 1
    assert row["observed_template_flow_contextual_edge_count"] == 0
    assert row["template_flow_evidence_state"] == "observed_in_assessed_sample"
    assert row["sitewide_template_flow_claim"] is False
    assert result["customer_fix_created"] is False


def test_template_contextual_opportunity_keeps_missing_template_flow_sample_scoped():
    pages, templates, graph, contextual = build_inputs(with_edge=False)

    result = template_contextual_internal_link_opportunities(templates, graph, contextual)

    row = candidate(result, pages[0]["url"], pages[1]["url"])
    assert row["observed_edge_present"] is False
    assert row["observed_template_flow_present"] is False
    assert row["observed_template_flow_directed_edge_count"] == 0
    assert row["observed_template_flow_contextual_edge_count"] == 0
    assert row["observed_template_flow_weight_sum"] == 0.0
    assert row["template_flow_evidence_state"] == "no_observed_flow_in_assessed_sample"
    assert result["sitewide_link_absence_claim"] is False
    assert result["sitewide_template_flow_claim"] is False


def test_template_contextual_opportunity_marks_same_template_pair_without_sitewide_claim():
    pages, templates, graph, contextual = build_inputs(with_edge=False, same_template=True)

    result = template_contextual_internal_link_opportunities(templates, graph, contextual)

    row = candidate(result, pages[0]["url"], pages[1]["url"])
    assert row["cross_template"] is False
    assert row["source_group_id"] == row["target_group_id"]
    assert row["source_template_key"] == row["target_template_key"]
    assert row["sitewide_template_flow_claim"] is False


def test_template_contextual_opportunity_rejects_foreign_candidate_population():
    _pages, templates, graph, contextual = build_inputs(with_edge=False)
    forged = deepcopy(contextual)
    forged["candidates"][0]["source_url"] = "https://foreign.test/page"

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_candidate_population_mismatch"
    assert result["template_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "verified"
    assert result["candidates"] == []


def test_template_contextual_opportunity_rejects_forged_graph_presence_claim():
    _pages, templates, graph, contextual = build_inputs(with_edge=True)
    forged = deepcopy(contextual)
    present = next(row for row in forged["candidates"] if row["observed_edge_present"] is True)
    present["observed_edge_present"] = False

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_candidate_edge_presence_mismatch"
    assert result["candidates"] == []


def test_template_contextual_opportunity_rejects_contextual_edge_candidate():
    pages, templates, _graph, contextual = build_inputs(with_edge=False)
    graph = build_weighted_internal_link_graph(
        pages,
        [link(pages[0]["url"], pages[1]["url"], zone="contextual")],
    )
    forged = deepcopy(contextual)
    row = next(
        row
        for row in forged["candidates"]
        if row["source_url"] == pages[0]["url"] and row["target_url"] == pages[1]["url"]
    )
    row["observed_edge_present"] = True
    row["existing_strongest_zone"] = "contextual"

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_candidate_already_contextual"
    assert result["candidates"] == []


def test_template_contextual_opportunity_rejects_duplicate_candidate_pair():
    _pages, templates, graph, contextual = build_inputs(with_edge=False)
    forged = deepcopy(contextual)
    forged["candidates"].append(deepcopy(forged["candidates"][0]))
    forged["candidate_count"] += 1

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_candidate_duplicate"


def test_template_contextual_opportunity_rejects_incomplete_semantic_pair_scan():
    _pages, templates, graph, contextual = build_inputs(with_edge=False)
    forged = deepcopy(contextual)
    forged["semantic_pair_scan_complete"] = False

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_opportunity_scan_incomplete"


def test_template_contextual_opportunity_rejects_inconsistent_truncation_flag():
    _pages, templates, graph, contextual = build_inputs(with_edge=False)
    forged = deepcopy(contextual)
    forged["candidates_truncated"] = True

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_opportunity_truncation_mismatch"


def test_template_contextual_opportunity_requires_explicit_existing_zone_field():
    _pages, templates, graph, contextual = build_inputs(with_edge=False)
    forged = deepcopy(contextual)
    forged["candidates"][0].pop("existing_strongest_zone")

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_candidate_existing_zone_missing"


def test_template_contextual_opportunity_rejects_forged_candidate_reason():
    _pages, templates, graph, contextual = build_inputs(with_edge=True)
    forged = deepcopy(contextual)
    row = next(item for item in forged["candidates"] if item["observed_edge_present"] is True)
    row["reason"] = "no_observed_edge_in_assessed_sample"

    result = template_contextual_internal_link_opportunities(templates, graph, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "contextual_candidate_reason_mismatch"


def test_template_contextual_opportunity_is_deterministic_and_non_mutating():
    _pages, templates, graph, contextual = build_inputs(with_edge=True)
    templates_before = deepcopy(templates)
    graph_before = deepcopy(graph)
    contextual_before = deepcopy(contextual)

    first = template_contextual_internal_link_opportunities(templates, graph, contextual)
    second = template_contextual_internal_link_opportunities(
        deepcopy(templates),
        deepcopy(graph),
        deepcopy(contextual),
    )

    assert first == second
    assert templates == templates_before
    assert graph == graph_before
    assert contextual == contextual_before
