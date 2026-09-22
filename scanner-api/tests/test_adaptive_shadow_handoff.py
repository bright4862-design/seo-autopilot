from __future__ import annotations

import copy
import hashlib
import json

from app.adaptive_shadow_handoff import build_adaptive_shadow_handoff


def fp(char: str) -> str:
    return char * 64


def lineage_certificate_fingerprint(lineage):
    identity = {
        "joint_evidence_fingerprint": lineage["joint_evidence_fingerprint"],
        "fix_corpus_fingerprint": lineage["fix_corpus_fingerprint"],
        "site_ids": lineage["site_ids"],
        "full_comparison_sites": lineage["full_comparison_sites"],
        "sites": lineage["sites"],
    }
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def joint_decision():
    return {
        "version": "adaptive_joint_evidence_decision_v1",
        "decision": "smart_500_joint_evidence_candidate",
        "reason": "ok",
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        "site_ids": ("a.example", "b.example"),
        "smart_500_population_fingerprints": (("a.example", fp("a")), ("b.example", fp("b"))),
        "full_comparison_sites": 1,
        "fix_corpus_fingerprint": fp("c"),
        "joint_evidence_fingerprint": fp("d"),
        "standard_150_contract": "unchanged_upstream_reference",
    }


def joint_lineage():
    lineage = {
        "version": "adaptive_joint_manifest_lineage_v1",
        "valid": True,
        "reason": "ok",
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        "joint_evidence_fingerprint": fp("d"),
        "fix_corpus_fingerprint": fp("c"),
        "site_ids": ("a.example", "b.example"),
        "full_comparison_sites": 1,
        "sites": (
            {
                "site_id": "a.example",
                "candidate_count": 1200,
                "selection_targets": (150, 500, 1000),
                "standard_150_pages": 150,
                "smart_500_pages": 500,
                "tail_1000_pages": 1000,
                "standard_150_population_fingerprint": fp("e"),
                "smart_500_population_fingerprint": fp("a"),
                "tail_1000_population_fingerprint": fp("f"),
                "comparison_state": "full_blind_1000_reference",
                "manifest_lineage_fingerprint": fp("1"),
            },
            {
                "site_id": "b.example",
                "candidate_count": 620,
                "selection_targets": (150, 500, 620),
                "standard_150_pages": 150,
                "smart_500_pages": 500,
                "tail_1000_pages": 620,
                "standard_150_population_fingerprint": fp("2"),
                "smart_500_population_fingerprint": fp("b"),
                "tail_1000_population_fingerprint": fp("3"),
                "comparison_state": "inventory_limited",
                "manifest_lineage_fingerprint": fp("4"),
            },
        ),
        "standard_150_preserved": True,
        "tranche_contract": (150, 500, 1000),
    }
    lineage["joint_manifest_lineage_fingerprint"] = lineage_certificate_fingerprint(lineage)
    return lineage


def test_builds_valid_shadow_handoff():
    result = build_adaptive_shadow_handoff(joint_decision(), joint_lineage())
    assert result["valid"] is True
    assert result["handoff_state"] == "shadow_candidate_only"
    assert result["tranche_contract"] == (150, 500, 1000)
    assert result["standard_150_contract"] == "unchanged_upstream_reference"
    assert result["production_budget_authorized"] is False
    assert result["execution_authorized"] is False
    assert result["requires_serialized_integrator"] is True
    assert len(result["handoff_fingerprint"]) == 64


def test_is_deterministic():
    first = build_adaptive_shadow_handoff(joint_decision(), joint_lineage())
    second = build_adaptive_shadow_handoff(joint_decision(), joint_lineage())
    assert first == second


def test_json_transport_is_stable():
    decision = json.loads(json.dumps(joint_decision()))
    lineage = json.loads(json.dumps(joint_lineage()))
    result = build_adaptive_shadow_handoff(decision, lineage)
    assert result["valid"] is True


def test_rejects_same_count_smart_population_transplant():
    lineage = joint_lineage()
    lineage["sites"][0]["smart_500_population_fingerprint"] = fp("9")
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["valid"] is False
    assert result["reason"] == "smart_500_population_mismatch"


def test_rejects_site_population_drift():
    lineage = joint_lineage()
    lineage["site_ids"] = ("a.example", "c.example")
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "site_population_mismatch"


def test_rejects_joint_evidence_identity_drift():
    lineage = joint_lineage()
    lineage["joint_evidence_fingerprint"] = fp("8")
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "joint_evidence_fingerprint_mismatch"


def test_rejects_fix_corpus_identity_drift():
    lineage = joint_lineage()
    lineage["fix_corpus_fingerprint"] = fp("8")
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "fix_corpus_fingerprint_mismatch"


def test_rejects_full_comparison_count_drift():
    lineage = joint_lineage()
    lineage["full_comparison_sites"] = 2
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "full_comparison_count_mismatch"


def test_rejects_nonpositive_joint_decision():
    decision = joint_decision()
    decision["decision"] = "blind_1000_joint_reference_retained"
    result = build_adaptive_shadow_handoff(decision, joint_lineage())
    assert result["reason"] == "joint_decision_not_positive_candidate"


def test_rejects_standard_150_contract_drift():
    decision = joint_decision()
    decision["standard_150_contract"] = "changed"
    result = build_adaptive_shadow_handoff(decision, joint_lineage())
    assert result["reason"] == "standard_150_contract_invalid"


def test_rejects_lineage_without_standard_150_preservation():
    lineage = joint_lineage()
    lineage["standard_150_preserved"] = False
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "standard_150_not_preserved"


def test_rejects_tranche_contract_drift():
    lineage = joint_lineage()
    lineage["tranche_contract"] = (150, 600, 1000)
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "tranche_contract_invalid"


def test_rejects_forged_authority_flags():
    decision = joint_decision()
    decision["production_budget_authorized"] = True
    result = build_adaptive_shadow_handoff(decision, joint_lineage())
    assert result["reason"] == "joint_decision_shadow_flags_invalid"


def test_rejects_malformed_lineage_fingerprint():
    lineage = joint_lineage()
    lineage["joint_manifest_lineage_fingerprint"] = "not-sha256"
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "handoff_identity_invalid"


def test_rejects_stale_joint_lineage_certificate_after_population_tamper():
    lineage = joint_lineage()
    lineage["sites"][0]["standard_150_population_fingerprint"] = fp("9")
    result = build_adaptive_shadow_handoff(joint_decision(), lineage)
    assert result["reason"] == "joint_manifest_lineage_fingerprint_mismatch"


def test_does_not_mutate_inputs():
    decision = joint_decision()
    lineage = joint_lineage()
    decision_before = copy.deepcopy(decision)
    lineage_before = copy.deepcopy(lineage)
    build_adaptive_shadow_handoff(decision, lineage)
    assert decision == decision_before
    assert lineage == lineage_before


def test_output_carries_exact_standard_and_tail_populations():
    result = build_adaptive_shadow_handoff(joint_decision(), joint_lineage())
    assert result["standard_150_population_fingerprints"] == (
        ("a.example", fp("e")),
        ("b.example", fp("2")),
    )
    assert result["tail_1000_population_fingerprints"] == (
        ("a.example", fp("f")),
        ("b.example", fp("3")),
    )
