from copy import deepcopy
from urllib.parse import urlparse

from app.adaptive_benchmark_bundle import (
    ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
    ADAPTIVE_BENCHMARK_BUNDLE_VERSION,
    build_adaptive_benchmark_bundle,
    summarize_adaptive_benchmark_bundle_corpus,
    validate_adaptive_benchmark_bundle,
)


def _family(url: str) -> str:
    path = urlparse(url).path
    return "product_page" if "/product/" in path else "blog"


def _path(url: str) -> str:
    return urlparse(url).path or "/"


def _urls(host: str, count: int):
    return [
        f"https://{host}/{'product' if index % 3 == 0 else 'guide'}/{index}"
        for index in range(count)
    ]


def _bundle(host: str = "x.test", count: int = 40):
    urls = _urls(host, count)
    return build_adaptive_benchmark_bundle(
        urls,
        _family,
        _path,
        finding_fingerprints_by_url={url: (f"finding-{index % 9}",) for index, url in enumerate(urls)},
        important_urls=[urls[0], urls[-1]],
        high_value_urls=[urls[0]],
    )


def test_bundle_binds_finding_and_priority_results_to_exact_populations():
    result = _bundle(count=1000)
    assert result["version"] == ADAPTIVE_BENCHMARK_BUNDLE_VERSION
    assert result["valid"] is True
    assert result["state"] == "observed"
    assert len(result["smart_selected"]) == 500
    assert len(result["blind_selected"]) == 1000
    assert len(result["smart_population_sha256"]) == 64
    assert len(result["blind_population_sha256"]) == 64
    assert result["finding_benchmark"]["smart_500"]["pages_assessed"] == 500
    assert result["priority_benchmark"]["smart_pages_assessed"] == 500
    assert validate_adaptive_benchmark_bundle(result)["valid"] is True
    assert result["population_scope_complete"] is False


def test_bundle_is_deterministic_for_same_exact_inputs():
    urls = _urls("det.test", 80)
    kwargs = {
        "finding_fingerprints_by_url": {url: (f"f-{index}",) for index, url in enumerate(urls)},
        "important_urls": [urls[2], urls[20]],
        "high_value_urls": [urls[2]],
    }
    first = build_adaptive_benchmark_bundle(urls, _family, _path, **kwargs)
    second = build_adaptive_benchmark_bundle(iter(urls), _family, _path, **kwargs)
    assert first == second


def test_bundle_preserves_exact_url_identity_distinctions():
    urls = [
        "https://x.test/x",
        "https://x.test/x/",
        "https://x.test/X",
    ]
    result = build_adaptive_benchmark_bundle(
        urls,
        _family,
        _path,
        finding_fingerprints_by_url={url: (url,) for url in urls},
        important_urls=urls,
    )
    assert result["valid"] is True
    assert result["smart_selected"] == tuple(urls)
    assert result["blind_selected"] == tuple(urls)
    assert result["priority_benchmark"]["important_reference_pages"] == 3
    assert result["priority_benchmark"]["important_reference_covered_by_smart"] == 3


def test_bundle_deduplicates_only_exact_duplicate_discovery_identities():
    urls = ["https://x.test/a", "https://x.test/a", "https://x.test/A"]
    result = build_adaptive_benchmark_bundle(
        urls,
        _family,
        _path,
        finding_fingerprints_by_url={},
        important_urls=[],
    )
    assert result["valid"] is True
    assert result["candidate_urls_supplied"] == 3
    assert result["candidate_urls_unique"] == 2
    assert result["duplicate_candidate_identities_removed"] == 1
    assert result["blind_selected"] == ("https://x.test/a", "https://x.test/A")


def test_bundle_rejects_ambiguous_candidate_identity_instead_of_normalizing_it():
    result = build_adaptive_benchmark_bundle(
        [" https://x.test/a"],
        _family,
        _path,
        finding_fingerprints_by_url={},
        important_urls=[],
    )
    assert result["valid"] is False
    assert result["reason"] == "candidate_urls_invalid_identity"


def test_bundle_validator_rejects_population_fingerprint_tampering():
    result = _bundle()
    tampered = deepcopy(result)
    tampered["smart_population_sha256"] = "0" * 64
    integrity = validate_adaptive_benchmark_bundle(tampered)
    assert integrity["valid"] is False
    assert integrity["reason"] == "smart_population_fingerprint_mismatch"


def test_bundle_validator_rejects_selected_population_tampering():
    result = _bundle()
    tampered = deepcopy(result)
    tampered["smart_selected"] = tuple(tampered["smart_selected"]) + ("https://foreign.test/page",)
    integrity = validate_adaptive_benchmark_bundle(tampered)
    assert integrity["valid"] is False
    assert integrity["reason"] == "smart_population_fingerprint_mismatch"


def test_bundle_validator_rejects_independently_valid_finding_count_drift():
    result = _bundle(count=40)
    tampered = deepcopy(result)
    smart = tampered["finding_benchmark"]["smart_500"]
    smart["pages_assessed"] = 39
    smart["finding_yield_per_100"] = round(smart["finding_fingerprints"] * 100.0 / 39, 4)
    tampered["finding_benchmark"]["pages_saved_by_smart"] = 1
    integrity = validate_adaptive_benchmark_bundle(tampered)
    assert integrity["valid"] is False
    assert integrity["reason"] == "finding_smart_population_count_mismatch"


def test_bundle_validator_rejects_independently_valid_priority_count_drift():
    result = _bundle(count=40)
    tampered = deepcopy(result)
    priority = tampered["priority_benchmark"]
    priority["smart_pages_assessed"] = 39
    priority["smart_pages_inside_blind"] = 39
    priority["smart_pages_outside_blind"] = 0
    integrity = validate_adaptive_benchmark_bundle(tampered)
    assert integrity["valid"] is False
    assert integrity["reason"] == "priority_smart_population_count_mismatch"


def test_bundle_corpus_is_deterministic_and_keeps_paired_populations():
    full = _bundle("full.test", 1000)
    limited = _bundle("limited.test", 30)
    summary = summarize_adaptive_benchmark_bundle_corpus({"z-site": limited, "a-site": full})
    assert summary["version"] == ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION
    assert summary["valid"] is True
    assert summary["site_ids"] == ("a-site", "z-site")
    assert summary["full_500_vs_1000_sites"] == 1
    assert summary["inventory_limited_sites"] == 1
    assert summary["smart_pages_assessed"] == 530
    assert summary["blind_pages_assessed"] == 1030
    assert summary["pages_saved_by_smart"] == 500
    assert tuple(item[0] for item in summary["population_fingerprints"]) == ("a-site", "z-site")
    assert summary["population_scope_complete"] is False


def test_bundle_corpus_fails_closed_on_invalid_member_or_site_identity():
    invalid = _bundle()
    invalid["blind_population_sha256"] = "bad"
    summary = summarize_adaptive_benchmark_bundle_corpus({"site": invalid})
    assert summary["valid"] is False
    assert summary["state"] == "invalid_benchmark"
    assert summary["invalid_sites"] == (("site", "blind_population_fingerprint_mismatch"),)

    summary = summarize_adaptive_benchmark_bundle_corpus({"": _bundle()})
    assert summary["valid"] is False
    assert summary["reason"] == "invalid_site_identity"


def test_bundle_corpus_requires_evidence():
    assert summarize_adaptive_benchmark_bundle_corpus({}) == {
        "version": ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION,
        "state": "insufficient_evidence",
        "valid": False,
        "reason": "no_bundles",
        "site_count": 0,
    }
