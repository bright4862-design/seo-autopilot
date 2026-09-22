from copy import deepcopy
import hashlib
import json

from app.adaptive_benchmark_bundle import build_adaptive_benchmark_bundle
from app.adaptive_manifest_benchmark_binding import (
    ADAPTIVE_MANIFEST_BENCHMARK_BINDING_INTEGRITY_VERSION,
    ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION,
    build_manifest_bound_benchmark_bundle,
    validate_manifest_bound_benchmark_bundle,
)
from app.adaptive_tranche_manifest import (
    build_adaptive_tranche_selection_manifest,
    validate_adaptive_tranche_selection_manifest,
)


def make_urls(count=1100, host="example.test"):
    return [f"https://{host}/section-{i % 11}/page-{i}" for i in range(count)]


def family_of(url):
    return url.split("/")[3]


def path_of(url):
    return "/" + "/".join(url.split("/")[3:])


def metadata(urls):
    return {
        url: {
            "high_value": i % 37 == 0,
            "template_novelty": (i % 5) / 4,
            "graph_novelty": (i % 3) / 2,
            "finding_affinity": (i % 7) / 6,
        }
        for i, url in enumerate(urls)
    }


def findings(urls):
    return {url: (f"finding-{i % 29}",) for i, url in enumerate(urls)}


def build_sources(urls):
    meta = metadata(urls)
    manifest = build_adaptive_tranche_selection_manifest(
        urls, family_of, path_of, metadata_by_url=meta
    )
    integrity = validate_adaptive_tranche_selection_manifest(
        manifest, urls, family_of, path_of, metadata_by_url=meta
    )
    bundle = build_adaptive_benchmark_bundle(
        urls,
        family_of,
        path_of,
        finding_fingerprints_by_url=findings(urls),
        important_urls=urls[:3],
        high_value_urls=urls[:1],
        metadata_by_url=meta,
    )
    return manifest, integrity, bundle


def benchmark_population_fingerprint(role, urls):
    payload = json.dumps(
        {
            "version": "adaptive_benchmark_population_v1",
            "role": role,
            "urls": tuple(urls),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_exact_manifest_smart_500_and_fifo_blind_1000_bind():
    urls = make_urls(1100)
    manifest, integrity, bundle = build_sources(urls)
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=integrity
    )
    assert artifact["version"] == ADAPTIVE_MANIFEST_BENCHMARK_BINDING_VERSION
    assert artifact["valid"] is True
    assert artifact["smart_pages"] == 500
    assert artifact["blind_pages"] == 1000
    assert artifact["manifest_smart_target"] == 500
    assert artifact["standard_150_preserved"] is True


def test_inventory_limited_620_uses_exact_500_smart_and_620_fifo_reference():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["smart_pages"] == 500
    assert artifact["blind_pages"] == 620
    assert artifact["manifest_smart_target"] == 500


def test_sub_500_inventory_binds_terminal_manifest_population():
    urls = make_urls(320)
    manifest, integrity, bundle = build_sources(urls)
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["smart_pages"] == 320
    assert artifact["blind_pages"] == 320
    assert artifact["manifest_smart_target"] == 320


def test_sub_150_inventory_preserves_exact_standard_reference():
    urls = make_urls(83)
    manifest, integrity, bundle = build_sources(urls)
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["standard_manifest_target"] == 83
    assert artifact["smart_pages"] == 83
    assert artifact["standard_150_preserved"] is True


def test_invalid_manifest_replay_integrity_fails_closed():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    bad = dict(integrity)
    bad["valid"] = False
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=bad
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_integrity_invalid"


def test_manifest_replay_identity_must_match_transported_manifest():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    bad = dict(integrity)
    bad["input_population_fingerprint"] = "0" * 64
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=bad
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_integrity_input_population_fingerprint_mismatch"


def test_discovery_order_drift_is_rejected_even_with_same_url_set():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    reordered = list(urls)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, reordered, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_input_population_mismatch"


def test_independently_valid_same_count_bundle_from_other_population_is_rejected():
    urls = make_urls(620)
    manifest, integrity, _ = build_sources(urls)
    other_urls = make_urls(620, host="other.test")
    _, _, other_bundle = build_sources(other_urls)
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, other_bundle, urls, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "smart_500_population_mismatch"


def test_reordered_blind_reference_is_rejected_even_with_recomputed_bundle_fingerprint():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    forged = deepcopy(bundle)
    blind = list(forged["blind_selected"])
    blind[0], blind[1] = blind[1], blind[0]
    forged["blind_selected"] = tuple(blind)
    forged["blind_population_sha256"] = benchmark_population_fingerprint(
        "blind_1000", forged["blind_selected"]
    )
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, forged, urls, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "blind_1000_population_mismatch"


def test_bundle_built_from_extra_duplicate_discovery_identity_is_rejected():
    urls = make_urls(620)
    manifest, integrity, _ = build_sources(urls)
    duplicate_transport = list(urls) + [urls[-1]]
    meta = metadata(duplicate_transport)
    duplicate_bundle = build_adaptive_benchmark_bundle(
        duplicate_transport,
        family_of,
        path_of,
        finding_fingerprints_by_url=findings(duplicate_transport),
        important_urls=duplicate_transport[:3],
        high_value_urls=duplicate_transport[:1],
        metadata_by_url=meta,
    )
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, duplicate_bundle, urls, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "benchmark_candidate_supplied_count_mismatch"


def test_forbidden_manifest_authority_claim_is_rejected():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    forged = dict(manifest)
    forged["production_budget_authorized"] = True
    artifact = build_manifest_bound_benchmark_bundle(
        forged, bundle, urls, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_forbidden_authority_claim"


def test_ambiguous_discovered_identity_is_rejected_without_normalization():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    malformed = list(urls)
    malformed[0] = " " + malformed[0]
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, malformed, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "discovered_urls_invalid_identity"


def test_binding_validator_accepts_json_like_transport_and_rejects_tamper():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=integrity
    )
    transported = json.loads(json.dumps(artifact))
    accepted = validate_manifest_bound_benchmark_bundle(
        transported, manifest, bundle, urls, manifest_integrity=integrity
    )
    assert accepted["version"] == ADAPTIVE_MANIFEST_BENCHMARK_BINDING_INTEGRITY_VERSION
    assert accepted["valid"] is True

    transported["blind_pages"] -= 1
    rejected = validate_manifest_bound_benchmark_bundle(
        transported, manifest, bundle, urls, manifest_integrity=integrity
    )
    assert rejected["valid"] is False
    assert rejected["reason"] == "artifact_mismatch"


def test_binding_is_shadow_only_and_does_not_mutate_inputs():
    urls = make_urls(620)
    manifest, integrity, bundle = build_sources(urls)
    before = (deepcopy(manifest), deepcopy(integrity), deepcopy(bundle), deepcopy(urls))
    artifact = build_manifest_bound_benchmark_bundle(
        manifest, bundle, urls, manifest_integrity=integrity
    )
    assert (manifest, integrity, bundle, urls) == before
    assert artifact["population_scope_complete"] is False
    assert artifact["production_budget_authorized"] is False
    assert artifact["site_fully_understood"] is False
