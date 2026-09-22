import copy

from app.adaptive_marginal_benchmark import (
    build_marginal_yield_benchmark,
    validate_marginal_yield_benchmark,
)
from app.adaptive_marginal_integrity import (
    ADAPTIVE_MARGINAL_POPULATION_INTEGRITY_VERSION,
    validate_marginal_population_integrity,
)


def _urls(n):
    return tuple(f"https://example.com/p/{i}" for i in range(n))


def _family(url):
    return "money" if int(url.rsplit("/", 1)[1]) % 7 == 0 else "content"


def _path(url):
    return "/" + "/".join(url.split("/", 3)[3:])


def _findings(urls):
    return {
        url: (f"f-{int(url.rsplit('/', 1)[1]) // 25}",)
        for url in urls
    }


def _build(n=1000):
    urls = _urls(n)
    return build_marginal_yield_benchmark(
        urls,
        _family,
        _path,
        finding_fingerprints_by_url=_findings(urls),
        template_key_by_url={
            url: f"t-{int(url.rsplit('/', 1)[1]) // 100}"
            for url in urls
        },
    )


def _rate(count, pages):
    if pages <= 0:
        return None
    return round(count * 100.0 / pages, 4)


def _coverage(covered, reference):
    if reference <= 0:
        return None
    return round(covered / reference, 4)


def test_valid_population_bound_benchmark_passes_without_authorizing_budget():
    result = _build()
    check = validate_marginal_population_integrity(result)
    assert check == {
        "version": ADAPTIVE_MARGINAL_POPULATION_INTEGRITY_VERSION,
        "valid": True,
        "reason": "ok",
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }


def test_rejects_non_hex_population_fingerprint_even_when_base_shape_passes():
    forged = copy.deepcopy(_build())
    forged["smart"][1]["population_fingerprint"] = "z" * 64
    assert validate_marginal_yield_benchmark(forged)["valid"] is True
    check = validate_marginal_population_integrity(forged)
    assert check["valid"] is False
    assert check["reason"] == "smart_population_fingerprint_invalid"


def test_rejects_underfilled_checkpoint_population_that_base_arithmetic_allows():
    forged = copy.deepcopy(_build())
    first = forged["smart"][0]
    first["pages_assessed"] = 149
    first["pages_added"] = 149
    first["new_finding_yield_per_100"] = _rate(
        first["new_finding_fingerprints"],
        149,
    )
    assert validate_marginal_yield_benchmark(forged)["valid"] is True
    check = validate_marginal_population_integrity(forged)
    assert check["valid"] is False
    assert check["reason"] == "smart_checkpoint_population_mismatch"


def test_rejects_discovery_cardinality_greater_than_pages():
    forged = copy.deepcopy(_build())
    final = forged["blind"][-1]
    previous = forged["blind"][-2]
    final["cumulative_template_keys"] = final["pages_assessed"] + 1
    final["new_template_keys"] = (
        final["cumulative_template_keys"] - previous["cumulative_template_keys"]
    )
    assert validate_marginal_yield_benchmark(forged)["valid"] is True
    check = validate_marginal_population_integrity(forged)
    assert check["valid"] is False
    assert check["reason"] == "blind_cumulative_template_keys_cardinality_invalid"


def test_inventory_limited_unchanged_population_must_keep_same_fingerprint():
    forged = copy.deepcopy(_build(300))
    assert forged["smart"][1]["pages_assessed"] == forged["smart"][2]["pages_assessed"] == 300
    forged["smart"][2]["population_fingerprint"] = "a" * 64
    if forged["smart"][1]["population_fingerprint"] == "a" * 64:
        forged["smart"][2]["population_fingerprint"] = "b" * 64
    assert validate_marginal_yield_benchmark(forged)["valid"] is True
    check = validate_marginal_population_integrity(forged)
    assert check["valid"] is False
    assert check["reason"] == "smart_unchanged_population_fingerprint_mismatch"


def test_expanded_population_cannot_reuse_prior_fingerprint():
    forged = copy.deepcopy(_build())
    forged["blind"][1]["population_fingerprint"] = forged["blind"][0]["population_fingerprint"]
    assert validate_marginal_yield_benchmark(forged)["valid"] is True
    check = validate_marginal_population_integrity(forged)
    assert check["valid"] is False
    assert check["reason"] == "blind_expanded_population_fingerprint_mismatch"


def test_full_inventory_smart_evidence_must_exactly_match_reference_population():
    forged = copy.deepcopy(_build())
    final = forged["smart"][-1]
    final["cumulative_finding_fingerprints"] -= 1
    final["new_finding_fingerprints"] -= 1
    final["reference_findings_covered"] -= 1
    final["new_finding_yield_per_100"] = _rate(
        final["new_finding_fingerprints"],
        final["pages_added"],
    )
    final["finding_coverage_vs_blind_1000"] = _coverage(
        final["reference_findings_covered"],
        forged["reference_finding_fingerprints"],
    )
    assert validate_marginal_yield_benchmark(forged)["valid"] is True
    check = validate_marginal_population_integrity(forged)
    assert check["valid"] is False
    assert check["reason"] == "smart_full_inventory_reference_findings_not_exact"


def test_integrity_wrapper_fails_closed_when_base_contract_is_invalid():
    forged = copy.deepcopy(_build())
    forged["blind"][2]["new_finding_yield_per_100"] = 999.0
    check = validate_marginal_population_integrity(forged)
    assert check["valid"] is False
    assert check["reason"] == "base:blind_finding_yield_mismatch"
    assert check["production_budget_authorized"] is False
    assert check["site_fully_understood"] is False
