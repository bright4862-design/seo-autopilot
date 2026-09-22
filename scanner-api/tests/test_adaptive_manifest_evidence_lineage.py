from copy import deepcopy
import json

from app.adaptive_manifest_evidence_lineage import (
    ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_INTEGRITY_VERSION,
    ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_VERSION,
    build_manifest_evidence_lineage,
    validate_manifest_evidence_lineage,
)


def fp(ch):
    return ch * 64


def bindings(candidate_count=1100, *, supplied=None, duplicates=0):
    supplied = candidate_count + duplicates if supplied is None else supplied
    pages150 = min(150, candidate_count)
    pages500 = min(500, candidate_count)
    pages1000 = min(1000, candidate_count)
    target150 = 150 if candidate_count >= 150 else candidate_count
    target500 = 500 if candidate_count >= 500 else candidate_count
    target1000 = 1000 if candidate_count >= 1000 else candidate_count
    marginal = {
        "version": "adaptive_manifest_marginal_binding_v1",
        "valid": True,
        "reason": "ok",
        "candidate_count": candidate_count,
        "input_population_fingerprint": fp("a"),
        "selection_targets": tuple(
            target for target in (target150, target500, target1000) if target > 0
        ),
        "bindings": (
            {
                "checkpoint": 150,
                "manifest_target": target150,
                "manifest_role": "standard_150",
                "pages_assessed": pages150,
                "population_fingerprint": fp("1"),
                "inventory_limited": pages150 < 150,
            },
            {
                "checkpoint": 500,
                "manifest_target": target500,
                "manifest_role": "adaptive_500",
                "pages_assessed": pages500,
                "population_fingerprint": fp("2"),
                "inventory_limited": pages500 < 500,
            },
            {
                "checkpoint": 1000,
                "manifest_target": target1000,
                "manifest_role": "adaptive_1000",
                "pages_assessed": pages1000,
                "population_fingerprint": fp("3"),
                "inventory_limited": pages1000 < 1000,
            },
        ),
        "binding_fingerprint": fp("b"),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    benchmark = {
        "version": "adaptive_manifest_benchmark_binding_v1",
        "valid": True,
        "reason": "benchmark_populations_bound_to_replay_manifest",
        "candidate_urls_supplied": supplied,
        "candidate_urls_unique": candidate_count,
        "duplicate_candidate_identities_removed": duplicates,
        "manifest_input_population_fingerprint": fp("a"),
        "manifest_smart_target": target500,
        "standard_manifest_target": target150,
        "smart_pages": pages500,
        "blind_pages": pages1000,
        "smart_population_sha256": fp("c"),
        "blind_population_sha256": fp("d"),
        "binding_fingerprint": fp("e"),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    marginal["selection_targets"] = tuple(sorted(set(marginal["selection_targets"])))
    return marginal, benchmark


def test_full_1100_population_cross_binding_reconciles():
    marginal, benchmark = bindings(1100)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["version"] == ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_VERSION
    assert artifact["valid"] is True
    assert artifact["standard_150_pages"] == 150
    assert artifact["smart_500_pages"] == 500
    assert artifact["blind_1000_pages"] == 1000
    assert artifact["comparison_state"] == "full_blind_1000_reference"
    assert artifact["standard_150_preserved"] is True


def test_620_population_is_inventory_limited_only_for_blind_reference():
    marginal, benchmark = bindings(620)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is True
    assert artifact["smart_500_pages"] == 500
    assert artifact["blind_1000_pages"] == 620
    assert artifact["comparison_state"] == "inventory_limited"


def test_sub_500_population_reconciles_terminal_smart_target():
    marginal, benchmark = bindings(320)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is True
    assert artifact["standard_150_pages"] == 150
    assert artifact["smart_500_pages"] == 320
    assert artifact["blind_1000_pages"] == 320


def test_sub_150_population_preserves_exact_terminal_standard_reference():
    marginal, benchmark = bindings(83)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is True
    assert artifact["standard_150_pages"] == 83
    assert artifact["smart_500_pages"] == 83
    assert artifact["blind_1000_pages"] == 83


def test_exact_duplicate_transport_counts_are_reconciled():
    marginal, benchmark = bindings(620, duplicates=7)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is True
    assert artifact["candidate_count"] == 620
    assert artifact["candidate_urls_supplied"] == 627
    assert artifact["duplicate_candidate_identities_removed"] == 7


def test_candidate_population_mismatch_is_rejected():
    marginal, benchmark = bindings(620)
    benchmark["candidate_urls_unique"] = 619
    benchmark["candidate_urls_supplied"] = 619
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "candidate_population_count_mismatch"


def test_duplicate_arithmetic_must_reconcile():
    marginal, benchmark = bindings(620, duplicates=3)
    benchmark["duplicate_candidate_identities_removed"] = 2
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "candidate_counts_invalid"


def test_cross_binding_input_population_fingerprint_mismatch_is_rejected():
    marginal, benchmark = bindings(620)
    benchmark["manifest_input_population_fingerprint"] = fp("f")
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "input_population_fingerprint_mismatch"


def test_noncanonical_sha256_shape_is_rejected():
    marginal, benchmark = bindings(620)
    marginal["binding_fingerprint"] = "A" * 64
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "binding_or_population_fingerprint_invalid"


def test_smart_500_checkpoint_count_drift_is_rejected():
    marginal, benchmark = bindings(620)
    forged = deepcopy(marginal)
    rows = list(forged["bindings"])
    rows[1] = dict(rows[1])
    rows[1]["pages_assessed"] = 499
    rows[1]["inventory_limited"] = True
    forged["bindings"] = tuple(rows)
    artifact = build_manifest_evidence_lineage(forged, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_checkpoint_500_page_count_mismatch"


def test_blind_reference_count_must_equal_bounded_candidate_inventory():
    marginal, benchmark = bindings(620)
    benchmark["blind_pages"] = 619
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "benchmark_blind_1000_page_count_mismatch"


def test_inventory_limited_manifest_target_drift_is_rejected():
    marginal, benchmark = bindings(320)
    rows = list(marginal["bindings"])
    rows[1] = dict(rows[1])
    rows[1]["manifest_target"] = 500
    marginal["bindings"] = tuple(rows)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_checkpoint_500_manifest_target_mismatch"


def test_benchmark_manifest_smart_target_drift_is_rejected():
    marginal, benchmark = bindings(320)
    benchmark["manifest_smart_target"] = 500
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "benchmark_manifest_smart_target_mismatch"


def test_duplicate_or_missing_marginal_checkpoint_is_rejected():
    marginal, benchmark = bindings(620)
    rows = list(marginal["bindings"])
    rows[2] = deepcopy(rows[1])
    marginal["bindings"] = tuple(rows)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_checkpoint_identity_invalid"


def test_forbidden_authority_claim_on_either_input_fails_closed():
    marginal, benchmark = bindings(620)
    marginal["production_budget_authorized"] = True
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_forbidden_authority_claim"

    marginal, benchmark = bindings(620)
    benchmark["site_fully_understood"] = True
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    assert artifact["valid"] is False
    assert artifact["reason"] == "benchmark_binding_forbidden_authority_claim"


def test_json_transport_validates_and_artifact_tamper_is_rejected():
    marginal, benchmark = bindings(1100)
    artifact = build_manifest_evidence_lineage(marginal, benchmark)
    transported = json.loads(json.dumps(artifact))
    accepted = validate_manifest_evidence_lineage(transported, marginal, benchmark)
    assert accepted["version"] == ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_INTEGRITY_VERSION
    assert accepted["valid"] is True
    assert accepted["lineage_fingerprint"] == artifact["lineage_fingerprint"]

    transported["smart_500_pages"] = 499
    rejected = validate_manifest_evidence_lineage(transported, marginal, benchmark)
    assert rejected["valid"] is False
    assert rejected["reason"] == "artifact_mismatch"


def test_lineage_is_deterministic_shadow_only_and_does_not_mutate_inputs():
    marginal, benchmark = bindings(1100)
    before = (deepcopy(marginal), deepcopy(benchmark))
    first = build_manifest_evidence_lineage(marginal, benchmark)
    second = build_manifest_evidence_lineage(marginal, benchmark)
    assert first == second
    assert (marginal, benchmark) == before
    assert first["population_scope_complete"] is False
    assert first["production_budget_authorized"] is False
    assert first["site_fully_understood"] is False
