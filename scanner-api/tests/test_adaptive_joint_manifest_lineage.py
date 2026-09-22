from copy import deepcopy
import json

from app.adaptive_joint_manifest_lineage import (
    ADAPTIVE_JOINT_MANIFEST_LINEAGE_VERSION,
    bind_joint_decision_to_manifest_lineage,
)


def _fp(char: str) -> str:
    return char * 64


def _joint(**overrides):
    result = {
        "version": "adaptive_joint_evidence_decision_v1",
        "decision": "smart_500_joint_evidence_candidate",
        "reason": "discovery_and_fix_evidence_agree_on_exact_smart_500_population",
        "site_ids": ("site-a", "site-b"),
        "smart_500_population_fingerprints": (
            ("site-a", _fp("b")),
            ("site-b", _fp("e")),
        ),
        "full_comparison_sites": 1,
        "fix_corpus_fingerprint": _fp("1"),
        "joint_evidence_fingerprint": _fp("2"),
        "standard_150_contract": "unchanged_upstream_reference",
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result.update(overrides)
    return result


def _lineage(site: str, *, candidate_count: int, smart_fp: str, full: bool, **overrides):
    suffix = "a" if site == "site-a" else "d"
    result = {
        "version": "adaptive_manifest_evidence_lineage_v1",
        "valid": True,
        "reason": "manifest_bound_evidence_lineage_reconciled",
        "candidate_count": candidate_count,
        "candidate_urls_supplied": candidate_count,
        "duplicate_candidate_identities_removed": 0,
        "input_population_fingerprint": _fp("9"),
        "selection_targets": (150, 500, 1000),
        "standard_150_pages": min(150, candidate_count),
        "smart_500_pages": min(500, candidate_count),
        "blind_1000_pages": min(1000, candidate_count),
        "marginal_population_fingerprints": (
            (150, _fp(suffix)),
            (500, smart_fp),
            (1000, _fp("c" if site == "site-a" else "f")),
        ),
        "benchmark_smart_population_sha256": _fp("7"),
        "benchmark_blind_population_sha256": _fp("8"),
        "marginal_binding_fingerprint": _fp("3"),
        "benchmark_binding_fingerprint": _fp("4"),
        "comparison_state": "full_blind_1000_reference" if full else "inventory_limited",
        "lineage_fingerprint": _fp("5" if site == "site-a" else "6"),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result.update(overrides)
    return result


def _lineages():
    return {
        "site-a": _lineage("site-a", candidate_count=1200, smart_fp=_fp("b"), full=True),
        "site-b": _lineage("site-b", candidate_count=620, smart_fp=_fp("e"), full=False),
    }


def test_positive_joint_candidate_binds_exact_150_500_1000_lineage():
    result = bind_joint_decision_to_manifest_lineage(_joint(), _lineages())
    assert result["version"] == ADAPTIVE_JOINT_MANIFEST_LINEAGE_VERSION
    assert result["valid"] is True
    assert result["reason"] == "joint_candidate_bound_to_exact_manifest_tranche_lineage"
    assert result["tranche_contract"] == (150, 500, 1000)
    assert result["standard_150_preserved"] is True
    assert result["full_comparison_sites"] == 1
    assert len(result["joint_manifest_lineage_fingerprint"]) == 64
    assert result["population_scope_complete"] is False
    assert result["production_budget_authorized"] is False
    assert result["site_fully_understood"] is False


def test_inventory_limited_site_keeps_exact_terminal_population_without_invention():
    result = bind_joint_decision_to_manifest_lineage(_joint(), _lineages())
    site_b = next(row for row in result["sites"] if row["site_id"] == "site-b")
    assert site_b["candidate_count"] == 620
    assert site_b["standard_150_pages"] == 150
    assert site_b["smart_500_pages"] == 500
    assert site_b["tail_1000_pages"] == 620
    assert site_b["comparison_state"] == "inventory_limited"


def test_same_count_different_smart_500_population_fails_closed():
    lineages = _lineages()
    lineages["site-b"] = _lineage(
        "site-b", candidate_count=620, smart_fp=_fp("7"), full=False
    )
    result = bind_joint_decision_to_manifest_lineage(_joint(), lineages)
    assert result["valid"] is False
    assert result["reason"] == "joint_smart_500_population_mismatch:site-b"


def test_standard_150_preservation_is_mandatory():
    lineages = _lineages()
    lineages["site-a"] = _lineage(
        "site-a", candidate_count=1200, smart_fp=_fp("b"), full=True,
        standard_150_preserved=False,
    )
    result = bind_joint_decision_to_manifest_lineage(_joint(), lineages)
    assert result["valid"] is False
    assert result["reason"] == "lineage_standard_150_not_preserved:site-a"


def test_joint_standard_150_contract_must_be_unchanged_reference():
    result = bind_joint_decision_to_manifest_lineage(
        _joint(standard_150_contract="adaptive_replaced_standard"), _lineages()
    )
    assert result["valid"] is False
    assert result["reason"] == "joint_decision_standard_150_contract_invalid"


def test_population_geometry_tampering_fails_closed():
    lineages = _lineages()
    lineages["site-b"] = _lineage(
        "site-b", candidate_count=620, smart_fp=_fp("e"), full=False,
        blind_1000_pages=1000,
    )
    result = bind_joint_decision_to_manifest_lineage(_joint(), lineages)
    assert result["valid"] is False
    assert result["reason"] == "lineage_tail_1000_page_count_mismatch:site-b"


def test_full_comparison_count_must_reconcile_with_manifest_lineages():
    result = bind_joint_decision_to_manifest_lineage(_joint(full_comparison_sites=2), _lineages())
    assert result["valid"] is False
    assert result["reason"] == "full_comparison_site_count_mismatch"


def test_lineage_site_population_must_exactly_match_joint_decision():
    lineages = _lineages()
    lineages["site-c"] = lineages.pop("site-b")
    result = bind_joint_decision_to_manifest_lineage(_joint(), lineages)
    assert result["valid"] is False
    assert result["reason"] == "lineage_site_population_mismatch"


def test_forged_authority_claim_is_rejected_from_joint_or_lineage():
    first = bind_joint_decision_to_manifest_lineage(
        _joint(production_budget_authorized=True), _lineages()
    )
    assert first["valid"] is False
    assert first["reason"] == "joint_decision_shadow_flags_invalid"

    lineages = _lineages()
    lineages["site-a"] = _lineage(
        "site-a", candidate_count=1200, smart_fp=_fp("b"), full=True,
        site_fully_understood=True,
    )
    second = bind_joint_decision_to_manifest_lineage(_joint(), lineages)
    assert second["valid"] is False
    assert second["reason"] == "lineage_shadow_flags_invalid:site-a"


def test_non_positive_joint_outcome_cannot_be_upgraded_to_certificate():
    result = bind_joint_decision_to_manifest_lineage(
        _joint(decision="blind_1000_joint_reference_retained"), _lineages()
    )
    assert result["valid"] is False
    assert result["reason"] == "joint_decision_not_positive_candidate"


def test_malformed_joint_and_lineage_fingerprints_fail_closed():
    first = bind_joint_decision_to_manifest_lineage(
        _joint(joint_evidence_fingerprint="bad"), _lineages()
    )
    assert first["valid"] is False
    assert first["reason"] == "joint_identity_or_full_comparison_count_invalid"

    lineages = _lineages()
    lineages["site-a"] = _lineage(
        "site-a", candidate_count=1200, smart_fp=_fp("b"), full=True,
        lineage_fingerprint="bad",
    )
    second = bind_joint_decision_to_manifest_lineage(_joint(), lineages)
    assert second["valid"] is False
    assert second["reason"] == "lineage_identity_invalid:site-a"


def test_selection_targets_must_be_strictly_increasing_and_bounded():
    lineages = _lineages()
    lineages["site-a"] = _lineage(
        "site-a", candidate_count=1200, smart_fp=_fp("b"), full=True,
        selection_targets=(150, 1000, 500),
    )
    result = bind_joint_decision_to_manifest_lineage(_joint(), lineages)
    assert result["valid"] is False
    assert result["reason"] == "lineage_identity_invalid:site-a"


def test_json_transport_preserves_certificate_identity():
    joint = json.loads(json.dumps(_joint()))
    lineages = json.loads(json.dumps(_lineages()))
    result = bind_joint_decision_to_manifest_lineage(joint, lineages)
    assert result["valid"] is True
    assert result["sites"][0]["site_id"] == "site-a"


def test_output_is_deterministic():
    first = bind_joint_decision_to_manifest_lineage(_joint(), _lineages())
    second = bind_joint_decision_to_manifest_lineage(_joint(), _lineages())
    assert first == second


def test_inputs_are_not_mutated():
    joint = _joint()
    lineages = _lineages()
    before = deepcopy((joint, lineages))
    bind_joint_decision_to_manifest_lineage(joint, lineages)
    assert (joint, lineages) == before
