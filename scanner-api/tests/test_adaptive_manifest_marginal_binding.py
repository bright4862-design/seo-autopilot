from copy import deepcopy

from app.adaptive_marginal_benchmark import build_marginal_yield_benchmark
from app.adaptive_tranche_manifest import (
    build_adaptive_tranche_selection_manifest,
    validate_adaptive_tranche_selection_manifest,
)
from app.adaptive_manifest_marginal_binding import (
    ADAPTIVE_MANIFEST_MARGINAL_BINDING_INTEGRITY_VERSION,
    ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION,
    build_manifest_bound_marginal_telemetry,
    validate_manifest_bound_marginal_telemetry,
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
    return {
        url: (f"finding-{i % 29}", f"route-{i % 13}")
        for i, url in enumerate(urls)
    }


def build_pair(urls):
    meta = metadata(urls)
    manifest = build_adaptive_tranche_selection_manifest(
        urls, family_of, path_of, metadata_by_url=meta
    )
    integrity = validate_adaptive_tranche_selection_manifest(
        manifest, urls, family_of, path_of, metadata_by_url=meta
    )
    marginal = build_marginal_yield_benchmark(
        urls,
        family_of,
        path_of,
        finding_fingerprints_by_url=findings(urls),
        metadata_by_url=meta,
    )
    return manifest, integrity, marginal


def test_default_150_500_1000_populations_bind_exactly():
    manifest, integrity, marginal = build_pair(make_urls(1100))
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    assert artifact["version"] == ADAPTIVE_MANIFEST_MARGINAL_BINDING_VERSION
    assert artifact["valid"] is True
    assert [row["checkpoint"] for row in artifact["bindings"]] == [150, 500, 1000]
    assert [row["manifest_target"] for row in artifact["bindings"]] == [150, 500, 1000]
    assert artifact["standard_150_preserved"] is True


def test_inventory_limited_620_binds_1000_checkpoint_to_terminal_620_population():
    manifest, integrity, marginal = build_pair(make_urls(620))
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["bindings"][-1]["checkpoint"] == 1000
    assert artifact["bindings"][-1]["manifest_target"] == 620
    assert artifact["bindings"][-1]["pages_assessed"] == 620
    assert artifact["bindings"][-1]["inventory_limited"] is True


def test_sub_150_inventory_binds_all_benchmark_checkpoints_to_exact_terminal_population():
    manifest, integrity, marginal = build_pair(make_urls(83))
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert [row["manifest_target"] for row in artifact["bindings"]] == [83, 83, 83]
    assert [row["pages_assessed"] for row in artifact["bindings"]] == [83, 83, 83]


def test_different_candidate_population_is_rejected_even_when_each_source_is_valid():
    manifest, integrity, _ = build_pair(make_urls(620))
    _, _, marginal = build_pair(make_urls(621, host="other.test"))
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "candidate_population_count_mismatch"


def test_same_count_transplanted_population_is_rejected_by_exact_fingerprint():
    manifest, integrity, _ = build_pair(make_urls(620))
    _, _, marginal = build_pair(make_urls(620, host="other.test"))
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "smart_checkpoint_150_population_mismatch"


def test_invalid_manifest_replay_integrity_fails_closed():
    manifest, integrity, marginal = build_pair(make_urls(620))
    bad = dict(integrity)
    bad["valid"] = False
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=bad
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_integrity_invalid"


def test_manifest_integrity_identity_must_match_manifest_transport():
    manifest, integrity, marginal = build_pair(make_urls(620))
    bad = dict(integrity)
    bad["input_population_fingerprint"] = "0" * 64
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=bad
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_integrity_input_population_fingerprint_mismatch"


def test_forged_smart_500_population_fingerprint_is_rejected():
    manifest, integrity, marginal = build_pair(make_urls(620))
    forged = deepcopy(marginal)
    forged["smart"] = list(forged["smart"])
    forged["smart"][1] = dict(forged["smart"][1])
    forged["smart"][1]["population_fingerprint"] = "1" * 64
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, forged, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "smart_checkpoint_500_population_mismatch"


def test_forbidden_manifest_authority_claim_is_rejected():
    manifest, integrity, marginal = build_pair(make_urls(620))
    forged = dict(manifest)
    forged["production_budget_authorized"] = True
    artifact = build_manifest_bound_marginal_telemetry(
        forged, marginal, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_forbidden_authority_claim"


def test_binding_artifact_is_shadow_only():
    manifest, integrity, marginal = build_pair(make_urls(620))
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    assert artifact["population_scope_complete"] is False
    assert artifact["production_budget_authorized"] is False
    assert artifact["site_fully_understood"] is False


def test_binding_validator_accepts_json_like_transport_and_rejects_tamper():
    manifest, integrity, marginal = build_pair(make_urls(620))
    artifact = build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    transported = deepcopy(artifact)
    transported["selection_targets"] = list(transported["selection_targets"])
    transported["checkpoints"] = list(transported["checkpoints"])
    transported["bindings"] = [dict(row) for row in transported["bindings"]]
    accepted = validate_manifest_bound_marginal_telemetry(
        transported, manifest, marginal, manifest_integrity=integrity
    )
    assert accepted["version"] == ADAPTIVE_MANIFEST_MARGINAL_BINDING_INTEGRITY_VERSION
    assert accepted["valid"] is True

    transported["bindings"][1]["pages_assessed"] += 1
    rejected = validate_manifest_bound_marginal_telemetry(
        transported, manifest, marginal, manifest_integrity=integrity
    )
    assert rejected["valid"] is False
    assert rejected["reason"] == "artifact_mismatch"


def test_inputs_are_not_mutated():
    manifest, integrity, marginal = build_pair(make_urls(620))
    manifest_before = deepcopy(manifest)
    integrity_before = deepcopy(integrity)
    marginal_before = deepcopy(marginal)
    build_manifest_bound_marginal_telemetry(
        manifest, marginal, manifest_integrity=integrity
    )
    assert manifest == manifest_before
    assert integrity == integrity_before
    assert marginal == marginal_before
