from app.adaptive_crawl import (
    ADAPTIVE_CRAWL_VERSION,
    ADAPTIVE_TELEMETRY_VERSION,
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


def test_tranche_plan_is_bounded_by_current_discovery_without_claiming_complete_site_knowledge():
    assert plan_tranche_targets(80)["targets"] == [80]
    assert plan_tranche_targets(320)["targets"] == [150, 320]
    plan = plan_tranche_targets(5000)
    assert plan["targets"] == [150, 500, 1000]
    assert plan["discovery_scope_complete"] is False
    assert plan["version"] == ADAPTIVE_CRAWL_VERSION


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
