import copy

import pytest

from app.adaptive_marginal_benchmark import (
    ADAPTIVE_MARGINAL_BENCHMARK_VERSION,
    ADAPTIVE_MARGINAL_GAP_VERSION,
    build_marginal_yield_benchmark,
    summarize_smart_500_gap,
    validate_marginal_yield_benchmark,
)


def _urls(n):
    return tuple(f"https://example.com/p/{i}" for i in range(n))


def _family(url):
    return "money" if int(url.rsplit("/", 1)[1]) % 7 == 0 else "content"


def _path(url):
    return "/" + "/".join(url.split("/", 3)[3:])


def _findings(urls):
    result = {}
    for url in urls:
        i = int(url.rsplit("/", 1)[1])
        values = [f"f-{i // 25}"]
        if i >= 500 and i % 50 == 0:
            values.append(f"tail-{i}")
        result[url] = tuple(values)
    return result


def _high(urls):
    return {
        url: ((f"h-{int(url.rsplit('/', 1)[1]) // 200}",) if int(url.rsplit("/", 1)[1]) % 20 == 0 else ())
        for url in urls
    }


def _build(n=1000, high=True):
    urls = _urls(n)
    return build_marginal_yield_benchmark(
        urls,
        _family,
        _path,
        finding_fingerprints_by_url=_findings(urls),
        high_impact_finding_fingerprints_by_url=_high(urls) if high else None,
        template_key_by_url={url: f"t-{int(url.rsplit('/', 1)[1]) // 100}" for url in urls},
        metadata_by_url={url: {"high_value": i % 13 == 0} for i, url in enumerate(urls)},
    )


def test_builds_deterministic_150_500_1000_curves():
    first = _build()
    second = _build()
    assert first == second
    assert first["version"] == ADAPTIVE_MARGINAL_BENCHMARK_VERSION
    assert first["checkpoints"] == (150, 500, 1000)
    assert [row["pages_assessed"] for row in first["blind"]] == [150, 500, 1000]
    assert [row["pages_added"] for row in first["blind"]] == [150, 350, 500]
    assert validate_marginal_yield_benchmark(first)["valid"] is True


def test_inventory_limited_site_reports_no_fake_incremental_pages():
    result = _build(300)
    assert result["inventory_limited"] is True
    assert [row["pages_assessed"] for row in result["blind"]] == [150, 300, 300]
    assert result["blind"][2]["state"] == "no_incremental_pages"
    assert result["blind"][2]["new_finding_yield_per_100"] is None
    gap = summarize_smart_500_gap(result)
    assert gap["state"] == "inventory_limited"
    assert gap["blind_tail_pages"] == 0


def test_high_impact_unknown_stays_unknown():
    result = _build(high=False)
    assert result["high_impact_evidence_state"] == "not_observed"
    assert result["reference_high_impact_finding_fingerprints"] is None
    for strategy in ("smart", "blind"):
        for row in result[strategy]:
            assert row["new_high_impact_finding_fingerprints"] is None
            assert row["high_impact_coverage_vs_blind_1000"] is None
    assert validate_marginal_yield_benchmark(result)["valid"] is True
    gap = summarize_smart_500_gap(result)
    assert gap["smart_500_missed_reference_high_impact_findings"] is None


def test_empty_reference_findings_do_not_become_zero_coverage():
    urls = _urls(1000)
    result = build_marginal_yield_benchmark(
        urls,
        _family,
        _path,
        finding_fingerprints_by_url={},
    )
    assert result["reference_finding_fingerprints"] == 0
    assert result["smart"][1]["finding_coverage_vs_blind_1000"] is None
    assert result["blind"][2]["finding_coverage_vs_blind_1000"] is None
    assert validate_marginal_yield_benchmark(result)["valid"] is True


def test_rejects_malformed_url_identity_instead_of_normalizing():
    with pytest.raises(ValueError, match="invalid_url_identity"):
        build_marginal_yield_benchmark(
            ["https://example.com/a", " https://example.com/b"],
            _family,
            _path,
            finding_fingerprints_by_url={},
        )


def test_exact_duplicate_urls_are_deduplicated_deterministically():
    urls = list(_urls(200))
    duplicated = urls[:50] + urls + urls[:10]
    result = build_marginal_yield_benchmark(
        duplicated,
        _family,
        _path,
        finding_fingerprints_by_url=_findings(urls),
    )
    assert result["candidate_count"] == 200
    assert result["reference_pages_assessed"] == 200
    assert validate_marginal_yield_benchmark(result)["valid"] is True


def test_gap_reports_blind_tail_marginal_findings_not_just_total_coverage():
    result = _build()
    gap = summarize_smart_500_gap(result)
    assert gap["version"] == ADAPTIVE_MARGINAL_GAP_VERSION
    assert gap["state"] == "observed"
    assert gap["blind_tail_pages"] == 500
    assert gap["blind_tail_new_findings"] > 0
    assert gap["blind_tail_new_finding_yield_per_100"] > 0
    assert gap["production_budget_authorized"] is False
    assert gap["site_fully_understood"] is False


def test_validator_rejects_forged_page_delta():
    result = _build()
    forged = copy.deepcopy(result)
    forged["smart"][1]["pages_added"] += 1
    check = validate_marginal_yield_benchmark(forged)
    assert check == {"valid": False, "reason": "smart_page_delta_mismatch"}


def test_validator_rejects_forged_finding_yield():
    result = _build()
    forged = copy.deepcopy(result)
    forged["blind"][2]["new_finding_yield_per_100"] = 999.0
    check = validate_marginal_yield_benchmark(forged)
    assert check == {"valid": False, "reason": "blind_finding_yield_mismatch"}


def test_validator_rejects_forged_cumulative_discovery_delta():
    result = _build()
    forged = copy.deepcopy(result)
    forged["smart"][1]["new_template_keys"] += 1
    check = validate_marginal_yield_benchmark(forged)
    assert check == {"valid": False, "reason": "smart_new_template_keys_delta_mismatch"}


def test_validator_rejects_false_reference_coverage():
    result = _build()
    forged = copy.deepcopy(result)
    forged["smart"][1]["finding_coverage_vs_blind_1000"] = 1.0
    if forged["smart"][1]["reference_findings_covered"] == forged["reference_finding_fingerprints"]:
        forged["smart"][1]["reference_findings_covered"] -= 1
    check = validate_marginal_yield_benchmark(forged)
    assert check["valid"] is False
    assert check["reason"] in {
        "smart_reference_finding_count_invalid",
        "smart_finding_coverage_mismatch",
    }


def test_validator_rejects_high_impact_metrics_when_not_observed():
    result = _build(high=False)
    forged = copy.deepcopy(result)
    forged["smart"][0]["new_high_impact_finding_fingerprints"] = 0
    check = validate_marginal_yield_benchmark(forged)
    assert check == {
        "valid": False,
        "reason": "smart_unexpected_high_impact_metric",
    }


def test_validator_rejects_reference_page_count_tampering():
    result = _build()
    forged = copy.deepcopy(result)
    forged["reference_pages_assessed"] = 999
    check = validate_marginal_yield_benchmark(forged)
    assert check == {"valid": False, "reason": "reference_page_count_mismatch"}


def test_inputs_are_not_mutated():
    urls = list(_urls(1000))
    findings = _findings(urls)
    metadata = {url: {"high_value": False} for url in urls}
    findings_before = copy.deepcopy(findings)
    metadata_before = copy.deepcopy(metadata)
    _ = build_marginal_yield_benchmark(
        urls,
        _family,
        _path,
        finding_fingerprints_by_url=findings,
        metadata_by_url=metadata,
    )
    assert findings == findings_before
    assert metadata == metadata_before
