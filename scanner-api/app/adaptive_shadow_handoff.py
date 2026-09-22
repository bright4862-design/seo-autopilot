"""Build a fail-closed shadow handoff for the serialized adaptive-crawl integrator.

This module does not execute a crawl or authorize a larger crawl budget. It only binds
an already-positive joint adaptive evidence decision to its exact replay-validated
150 -> 500 -> 1000 manifest-lineage certificate and emits a deterministic engineering
handoff envelope. Standard 150 remains an unchanged upstream reference.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION = "adaptive_joint_evidence_decision_v1"
ADAPTIVE_JOINT_MANIFEST_LINEAGE_VERSION = "adaptive_joint_manifest_lineage_v1"
ADAPTIVE_SHADOW_HANDOFF_VERSION = "adaptive_shadow_handoff_v1"
TRANCHE_CONTRACT = (150, 500, 1000)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _result(valid: bool, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_SHADOW_HANDOFF_VERSION,
        "valid": valid,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        "execution_authorized": False,
        "requires_serialized_integrator": True,
        **extra,
    }


def _shadow_flags_valid(envelope: Mapping[str, Any]) -> bool:
    return all(
        envelope.get(field) is False
        for field in (
            "population_scope_complete",
            "production_budget_authorized",
            "site_fully_understood",
        )
    )


def _sha256(value: Any) -> str | None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        return None
    return value


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _site_ids(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    result = tuple(value)
    if (
        not result
        or any(not isinstance(site_id, str) or not site_id or site_id.strip() != site_id for site_id in result)
        or len(set(result)) != len(result)
        or result != tuple(sorted(result))
    ):
        return None
    return result


def _pair_fingerprints(value: Any, site_ids: tuple[str, ...]) -> tuple[tuple[str, str], ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    rows = tuple(value)
    if len(rows) != len(site_ids):
        return None
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence):
            return None
        parts = tuple(row)
        if len(parts) != 2:
            return None
        site_id, fingerprint = parts
        if not isinstance(site_id, str) or site_id in seen or _sha256(fingerprint) is None:
            return None
        seen.add(site_id)
        normalized.append((site_id, fingerprint))
    normalized.sort(key=lambda item: item[0])
    result = tuple(normalized)
    if tuple(site_id for site_id, _ in result) != site_ids:
        return None
    return result


def _tranche_contract(value: Any) -> tuple[int, int, int] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    parsed = tuple(value)
    if parsed != TRANCHE_CONTRACT:
        return None
    return TRANCHE_CONTRACT


def _lineage_sites(
    value: Any, site_ids: tuple[str, ...]
) -> tuple[tuple[str, str, str, str, str], ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    rows = tuple(value)
    if len(rows) != len(site_ids):
        return None
    normalized: list[tuple[str, str, str, str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            return None
        site_id = row.get("site_id")
        standard_fp = _sha256(row.get("standard_150_population_fingerprint"))
        smart_fp = _sha256(row.get("smart_500_population_fingerprint"))
        tail_fp = _sha256(row.get("tail_1000_population_fingerprint"))
        manifest_fp = _sha256(row.get("manifest_lineage_fingerprint"))
        if (
            not isinstance(site_id, str)
            or site_id in seen
            or standard_fp is None
            or smart_fp is None
            or tail_fp is None
            or manifest_fp is None
        ):
            return None
        seen.add(site_id)
        normalized.append((site_id, standard_fp, smart_fp, tail_fp, manifest_fp))
    normalized.sort(key=lambda item: item[0])
    result = tuple(normalized)
    if tuple(site_id for site_id, *_ in result) != site_ids:
        return None
    return result


def _fingerprint_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(ADAPTIVE_SHADOW_HANDOFF_VERSION.encode("utf-8"))
    digest.update(b"\0")
    digest.update(encoded)
    return digest.hexdigest()


def build_adaptive_shadow_handoff(
    joint_decision: Mapping[str, Any] | Any,
    joint_lineage: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Bind positive adaptive evidence to exact manifest lineage for integrator review.

    The returned handoff is evidence transport only. Even a valid handoff sets
    ``execution_authorized`` and ``production_budget_authorized`` to ``False``.
    """
    if not isinstance(joint_decision, Mapping):
        return _result(False, "joint_decision_not_mapping")
    if not isinstance(joint_lineage, Mapping):
        return _result(False, "joint_lineage_not_mapping")
    if joint_decision.get("version") != ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION:
        return _result(False, "joint_decision_version_mismatch")
    if joint_lineage.get("version") != ADAPTIVE_JOINT_MANIFEST_LINEAGE_VERSION:
        return _result(False, "joint_lineage_version_mismatch")
    if not _shadow_flags_valid(joint_decision):
        return _result(False, "joint_decision_shadow_flags_invalid")
    if not _shadow_flags_valid(joint_lineage):
        return _result(False, "joint_lineage_shadow_flags_invalid")
    if joint_decision.get("decision") != "smart_500_joint_evidence_candidate":
        return _result(False, "joint_decision_not_positive_candidate")
    if joint_lineage.get("valid") is not True:
        return _result(False, "joint_lineage_invalid")
    if joint_decision.get("standard_150_contract") != "unchanged_upstream_reference":
        return _result(False, "standard_150_contract_invalid")
    if joint_lineage.get("standard_150_preserved") is not True:
        return _result(False, "standard_150_not_preserved")
    if _tranche_contract(joint_lineage.get("tranche_contract")) is None:
        return _result(False, "tranche_contract_invalid")

    decision_sites = _site_ids(joint_decision.get("site_ids"))
    lineage_sites_ids = _site_ids(joint_lineage.get("site_ids"))
    if decision_sites is None or lineage_sites_ids is None:
        return _result(False, "site_population_invalid")
    if decision_sites != lineage_sites_ids:
        return _result(False, "site_population_mismatch")

    decision_smart = _pair_fingerprints(
        joint_decision.get("smart_500_population_fingerprints"), decision_sites
    )
    lineage_rows = _lineage_sites(joint_lineage.get("sites"), decision_sites)
    if decision_smart is None or lineage_rows is None:
        return _result(False, "population_fingerprint_set_invalid")
    lineage_smart = tuple((site_id, smart_fp) for site_id, _, smart_fp, _, _ in lineage_rows)
    if decision_smart != lineage_smart:
        return _result(False, "smart_500_population_mismatch")

    decision_full = _positive_int(joint_decision.get("full_comparison_sites"))
    lineage_full = _positive_int(joint_lineage.get("full_comparison_sites"))
    if decision_full is None or lineage_full is None:
        return _result(False, "full_comparison_count_invalid")
    if decision_full != lineage_full or decision_full > len(decision_sites):
        return _result(False, "full_comparison_count_mismatch")

    decision_joint_fp = _sha256(joint_decision.get("joint_evidence_fingerprint"))
    lineage_joint_fp = _sha256(joint_lineage.get("joint_evidence_fingerprint"))
    decision_fix_fp = _sha256(joint_decision.get("fix_corpus_fingerprint"))
    lineage_fix_fp = _sha256(joint_lineage.get("fix_corpus_fingerprint"))
    lineage_certificate_fp = _sha256(joint_lineage.get("joint_manifest_lineage_fingerprint"))
    if None in (
        decision_joint_fp,
        lineage_joint_fp,
        decision_fix_fp,
        lineage_fix_fp,
        lineage_certificate_fp,
    ):
        return _result(False, "handoff_identity_invalid")
    if decision_joint_fp != lineage_joint_fp:
        return _result(False, "joint_evidence_fingerprint_mismatch")
    if decision_fix_fp != lineage_fix_fp:
        return _result(False, "fix_corpus_fingerprint_mismatch")

    site_lineage_fingerprints = tuple(
        (site_id, manifest_fp) for site_id, _, _, _, manifest_fp in lineage_rows
    )
    standard_populations = tuple(
        (site_id, standard_fp) for site_id, standard_fp, _, _, _ in lineage_rows
    )
    tail_populations = tuple((site_id, tail_fp) for site_id, _, _, tail_fp, _ in lineage_rows)

    identity = {
        "joint_evidence_fingerprint": decision_joint_fp,
        "fix_corpus_fingerprint": decision_fix_fp,
        "joint_manifest_lineage_fingerprint": lineage_certificate_fp,
        "site_ids": decision_sites,
        "smart_500_population_fingerprints": decision_smart,
        "standard_150_population_fingerprints": standard_populations,
        "tail_1000_population_fingerprints": tail_populations,
        "site_manifest_lineage_fingerprints": site_lineage_fingerprints,
        "full_comparison_sites": decision_full,
        "tranche_contract": TRANCHE_CONTRACT,
    }
    return _result(
        True,
        "positive_joint_evidence_bound_for_serialized_integrator_review",
        **identity,
        handoff_fingerprint=_fingerprint_json(identity),
        standard_150_contract="unchanged_upstream_reference",
        handoff_state="shadow_candidate_only",
        requested_integrator_action="review_only_no_automatic_expansion",
    )
