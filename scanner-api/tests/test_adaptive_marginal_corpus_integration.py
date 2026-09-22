from app.adaptive_marginal_benchmark import build_marginal_yield_benchmark
from app.adaptive_marginal_corpus import summarize_marginal_gap_corpus


def _path_of(url):
    return url.split("x.test", 1)[1]


def test_marginal_corpus_accepts_real_strict_population_validated_benchmark():
    urls = [f"https://x.test/products/{index}" for index in range(1000)]
    findings = {
        url: {f"finding:{index // 100}"}
        for index, url in enumerate(urls)
        if index % 100 == 0
    }
    high_impact = {
        urls[100]: {"high:early"},
        urls[900]: {"high:tail"},
    }
    templates = {url: "product" for url in urls}

    result = build_marginal_yield_benchmark(
        urls,
        lambda url: "product_page",
        _path_of,
        finding_fingerprints_by_url=findings,
        high_impact_finding_fingerprints_by_url=high_impact,
        template_key_by_url=templates,
    )
    corpus = summarize_marginal_gap_corpus({"fixture.test": result})

    assert corpus["valid"] is True
    assert corpus["state"] == "observed"
    assert corpus["full_500_vs_1000_sites"] == 1
    assert corpus["inventory_limited_sites"] == 0
    assert corpus["high_impact_evidence_state"] == "observed"
    assert corpus["full_blind_tail_pages"] == 500
    assert corpus["population_scope_complete"] is False
    assert corpus["production_budget_authorized"] is False
    assert corpus["site_fully_understood"] is False
