from app.adaptive_crawl import (
    ADAPTIVE_CRAWL_VERSION,
    ADAPTIVE_TELEMETRY_VERSION,
    MAX_ADAPTIVE_TARGET,
    benchmark_smart_500_vs_blind_1000,
    build_tranche_yield_telemetry,
    continuation_decision,
    plan_tranche_targets,
    select_adaptive_urls,
)
from app.sampling import select_balanced_urls


def _fixture():
    urls = []
    family = {}
    template = {}
    findings = {}
    metadata = {}

    def add(prefix, count, fam, template_key, finding_every=0, high_value=False):
        for i in range(count):
            url = f"https://x.test/{prefix}/{i}"
            urls.append(url)
            family[url] = fam
            template[url] = template_key
            metadata[url] = {
                "template_novelty": 1.0 if i == 0 else 0.0,
                "graph_novelty": 1.0 if i < 3 else 0.0,
                "high_value": high_value,
            }
            if finding_every and i % finding_every == 0:
                findings[url] = {f"{fam}:issue:{i % 7}"}

    add("products", 900, "product_page", "product", finding_every=90, high_value=True)
    add("guides", 350, "guide_article", "guide", finding_every=70)
    add("locations", 220, "location_landing", "location", finding_every=44, high_value=True)
    add("compare", 120, "comparison_page", "comparison", finding_every=24, high_value=True)
    add("legal", 20, "legal_info", "legal", finding_every=10)
    return urls, family, template, findings, metadata


def _family_of(mapping):
    return lambda url: mapping[url]


def _path_of(url):
    return url.split("x.test", 1)[1]


def _observed_snapshot(assessed_count, *, route_count=1, template_count=1, graph_count=1, finding_count=1):
    return {
        "assessed_count": assessed_count,
        "route_signatures": {f"r{i}" for i in range(route_count)},
        "template_keys": {f"t{i}" for i in range(template_count)},
        "graph_edges": {f"e{i}" for i in range(graph_count)},
        "finding_fingerprints": {f"f{i}" for i in range(finding_count)},
        "high_impact_finding_fingerprints": {f"h{i}" for i in range(finding_count)},
        "high_value_families_assessed": {"product_page"},
    }


def test_standard_150_selection_is_byte_for_byte_existing_sampling_order():
    urls, family, _, _, metadata = _fixture()
    expected = select_balanced_urls(urls, _family_of(family), _path_of, 150)
    actual = select_adaptive_urls(
        urls,
        _family_of(family),
        _path_of,
        150,
        metadata_by_url=metadata,
    )
    assert actual == expected


def test_selection_is_bounded_deterministic_and_keeps_baseline_prefix():
    urls, family, _, _, metadata = _fixture()
    baseline = select_balanced_urls(urls, _family_of(family), _path_of, 150)
    first = select_adaptive_urls(urls, _family_of(family), _path_of, 500, metadata_by_url=metadata)
    second = select_adaptive_urls(urls, _family_of(family), _path_of, 500, metadata_by_url=metadata)
    assert first == second
    assert len(first) == len(set(first)) == 500
    assert first[:150] == baseline


def test_selector_hard_caps_even_if_caller_requests_more_than_nextgen_contract():
    urls, family, _, _, metadata = _fixture()
    selected = select_adaptive_urls(
        urls,
        _family_of(family),
        _path_of,
        5000,
        metadata_by_url=metadata,
    )
    assert len(selected) == MAX_ADAPTIVE_TARGET == 1000


def test_tranche_plan_is_bounded_by_current_discovery_without_claiming_complete_site_knowledge():
    assert plan_tranche_targets(80)["targets"] == [80]
    assert plan_tranche_targets(320)["targets"] == [150, 320]
    plan = plan_tranche_targets(5000)
    assert plan["targets"] == [150, 500, 1000]
    assert plan["requested_ceiling"] == 1000
    assert plan["assessment_ceiling"] == 1000
    assert plan["discovery_scope_complete"] is False
    assert plan["version"] == ADAPTIVE_CRAWL_VERSION


def test_tranche_plan_hard_caps_requested_ceiling_and_supports_shadow_intermediate_targets():
    plan = plan_tranche_targets(
        5000,
        ceiling=5000,
        candidate_targets=(150, 300, 500, 750, 1000, 2500),
    )
    assert plan["requested_ceiling"] == 5000
    assert plan["assessment_ceiling"] == 1000
    assert plan["targets"] == [150, 300, 500, 750, 1000]


def test_yield_telemetry_preserves_unknown_instead_of_coercing_it_to_zero():
    telemetry = build_tranche_yield_telemetry(
        {"assessed_count": 150, "route_signatures": {"a"}},
        {"assessed_count": 500, "route_signatures": {"a", "b"}},
        discovered_urls=2000,
    )
    assert telemetry["version"] == ADAPTIVE_TELEMETRY_VERSION
    assert telemetry["new_route_signatures"] == 1
    assert telemetry["new_template_keys"] is None
    assert telemetry["signal_state"] == "insufficient_evidence"
    decision = continuation_decision(telemetry)
    assert decision["decision"] == "insufficient_evidence"
    assert decision["site_fully_understood"] is False


def test_invalid_assessed_counts_fail_closed_instead_of_authorizing_expansion():
    previous = _observed_snapshot(500)
    current = _observed_snapshot(1001, route_count=50, template_count=10, graph_count=100, finding_count=20)
    telemetry = build_tranche_yield_telemetry(previous, current, discovered_urls=900)
    assert telemetry["counts_valid"] is False
    assert telemetry["signal_state"] == "invalid_counts"
    decision = continuation_decision(telemetry)
    assert decision["decision"] == "hold"
    assert decision["reason"] == "adaptive_ceiling_reached"
    assert decision["next_target"] is None


def test_continuation_expands_on_measured_novelty_not_just_a_large_discovered_count():
    previous = {
        "assessed_count": 150,
        "route_signatures": {f"r{i}" for i in range(40)},
        "template_keys": {"product", "guide"},
        "graph_edges": {f"e{i}" for i in range(80)},
        "finding_fingerprints": {"f1", "f2"},
        "high_impact_finding_fingerprints": {"f1"},
        "high_value_families_assessed": {"product_page"},
    }
    current = {
        "assessed_count": 500,
        "route_signatures": {f"r{i}" for i in range(80)},
        "template_keys": {"product", "guide", "location", "comparison"},
        "graph_edges": {f"e{i}" for i in range(140)},
        "finding_fingerprints": {"f1", "f2", "f3", "f4", "f5"},
        "high_impact_finding_fingerprints": {"f1", "f3", "f4"},
        "high_value_families_assessed": {"product_page", "location_landing"},
    }
    telemetry = build_tranche_yield_telemetry(previous, current, discovered_urls=1800)
    decision = continuation_decision(telemetry)
    assert telemetry["signal_state"] == "observed"
    assert decision["decision"] == "expand"
    assert decision["next_target"] == 1000
    assert "route_novelty" in decision["reason"]


def test_continuation_holds_when_marginal_yield_is_observed_and_flat():
    previous = {
        "assessed_count": 150,
        "route_signatures": {"a"},
        "template_keys": {"product"},
        "graph_edges": {"e1"},
        "finding_fingerprints": {"f1"},
        "high_impact_finding_fingerprints": {"f1"},
        "high_value_families_assessed": {"product_page"},
    }
    current = {
        "assessed_count": 500,
        "route_signatures": {"a", "b"},
        "template_keys": {"product"},
        "graph_edges": {"e1", "e2"},
        "finding_fingerprints": {"f1"},
        "high_impact_finding_fingerprints": {"f1"},
        "high_value_families_assessed": {"product_page"},
    }
    decision = continuation_decision(build_tranche_yield_telemetry(previous, current, discovered_urls=1800))
    assert decision["decision"] == "hold"
    assert decision["next_target"] is None
    assert decision["site_fully_understood"] is False


def test_continuation_never_escapes_1000_page_contract_after_ceiling_is_reached():
    previous = _observed_snapshot(500)
    current = _observed_snapshot(1000, route_count=80, template_count=20, graph_count=200, finding_count=30)
    telemetry = build_tranche_yield_telemetry(previous, current, discovered_urls=5000)
    assert telemetry["signal_state"] == "observed"
    decision = continuation_decision(telemetry)
    assert decision == {
        "version": ADAPTIVE_CRAWL_VERSION,
        "decision": "hold",
        "next_target": None,
        "reason": "adaptive_ceiling_reached",
        "site_fully_understood": False,
    }


def test_continuation_uses_partial_discovered_inventory_without_skipping_to_1000():
    previous = _observed_snapshot(150)
    current = _observed_snapshot(300, route_count=20, template_count=8, graph_count=30, finding_count=10)
    telemetry = build_tranche_yield_telemetry(previous, current, discovered_urls=420)
    decision = continuation_decision(telemetry, tranche_targets=(150, 500, 1000))
    assert decision["decision"] == "expand"
    assert decision["next_target"] == 420


def test_smart_500_benchmark_has_higher_finding_efficiency_than_blind_1000():
    urls, family, template, findings, metadata = _fixture()
    result = benchmark_smart_500_vs_blind_1000(
        urls,
        _family_of(family),
        _path_of,
        finding_fingerprints_by_url=findings,
        template_key_by_url=template,
        metadata_by_url=metadata,
    )
    assert result["smart_500"]["pages_assessed"] == 500
    assert result["blind_1000"]["pages_assessed"] == 1000
    assert result["smart_efficiency_vs_blind"] > 1.0
    assert result["smart_500"]["families"] >= result["blind_1000"]["families"]
    assert result["pages_saved_by_smart"] == 500
    assert result["finding_comparison_state"] == "observed"


def test_benchmark_does_not_fabricate_ratios_when_blind_sample_has_no_findings():
    urls = [f"https://x.test/page/{i}" for i in range(1200)]
    family = {url: "guide_article" for url in urls}
    result = benchmark_smart_500_vs_blind_1000(
        urls,
        _family_of(family),
        _path_of,
        finding_fingerprints_by_url={},
    )
    assert result["smart_finding_coverage_vs_blind"] is None
    assert result["smart_efficiency_vs_blind"] is None
    assert result["finding_comparison_state"] == "no_blind_findings"
    assert result["shared_finding_fingerprints"] == 0
    assert result["smart_only_finding_fingerprints"] == 0
    assert result["blind_only_finding_fingerprints"] == 0
