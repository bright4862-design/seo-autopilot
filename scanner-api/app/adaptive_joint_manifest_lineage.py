"""Bind a positive joint adaptive decision back to exact manifest tranche lineage.

The joint adaptive evidence decision proves that discovery/marginal evidence and Fix
benchmark evidence agree on Smart 500. This pure shadow helper closes the remaining
lineage loop by requiring every site in that positive decision to resolve to a valid
manifest evidence lineage for the exact 150 -> 500 -> 1000 populations.

It performs no crawling, ranking, persistence, authority, customer projection, budget
mutation, admission, release, deployment, or network work. A valid certificate is
engineering evidence only and never authorizes production.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION = "adaptive_joint_evidence_decision_v1"
ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_VERSION = "adaptive_manifest_evidence_lineage_v1"
ADAPTIVE_JOINT_MANIFEST_LINEAGE_VERSION = "adaptive_joint_manifest_lineage_v1"
STANDARD_TARGET = 150
SMART_TARGET = 500
TAIL_TARGET = 1000
CHECKPOINTS = (STANDARD_TARGET, SMART_TARGET, TAIL_TARGET)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _result(valid: bool, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_JOINT_MANIFEST_LINEAGE_VERSION,
        "valid": valid,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        **extra,
    }


def _sha256(value: Any) -> str | None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        return None
    return value


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
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


def _shadow_flags_valid(envelope: Mapping[str, Any]) -> bool:
    return all(
        envelope.get(field) is False
        for field in (
            "population_scope_complete",
            "production_budget_authorized",
            "site_fully_understood",
        )
    )


def _smart_fingerprints(value: Any, site_ids: tuple[str, ...]) -> dict[str, str] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    rows = tuple(value)
    if len(rows) != len(site_ids):
        return None
    result: dict[str, str] = {}
    for row in rows:
        if isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence):
            return None
        parts = tuple(row)
        if len(parts) != 2:
            return None
        site_id, fingerprint = parts
        if (
            not isinstance(site_id, str)
            or site_id in result
            or _sha256(fingerprint) is None
        ):
            return None
        result[site_id] = fingerprint
    if tuple(sorted(result)) != site_ids:
        return None
    return result


def _checkpoint_fingerprints(value: Any) -> dict[int, str] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    rows = tuple(value)
    if len(rows) != len(CHECKPOINTS):
        return None
    result: dict[int, str] = {}
    for row in rows:
        if isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence):
            return None
        parts = tuple(row)
        if len(parts) != 2:
            return None
        checkpoint, fingerprint = parts
        if checkpoint not in CHECKPOINTS or checkpoint in result or _sha256(fingerprint) is None:
            return None
        result[checkpoint] = fingerprint
    if tuple(sorted(result)) != CHECKPOINTS:
        return None
    return result


def _selection_targets(value: Any) -> tuple[int, ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    targets: list[int] = []
    for raw in value:
        parsed = _nonnegative_int(raw)
        if parsed is None or parsed <= 0 or parsed > TAIL_TARGET:
            return None
        targets.append(parsed)
    result = tuple(targets)
    if result != tuple(sorted(set(result))):
        return None
    return result


def _fingerprint_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bind_joint_decision_to_manifest_lineage(
    joint_decision: Mapping[str, Any] | Any,
    lineages_by_site: Mapping[str, Mapping[str, Any]] | Any,
) -> dict[str, Any]:
    """Return a fail-closed certificate for exact 150/500/1000 decision lineage.

    Only a positive ``smart_500_joint_evidence_candidate`` can be certified. The site
    set, exact Smart-500 population fingerprints, full-comparison count, Standard-150
    preservation, and every manifest checkpoint fingerprint must reconcile.
    """
    if not isinstance(joint_decision, Mapping):
        return _result(False, "joint_decision_not_mapping")
    if joint_decision.get("version") != ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION:
        return _result(False, "joint_decision_version_mismatch")
    if not _shadow_flags_valid(joint_decision):
        return _result(False, "joint_decision_shadow_flags_invalid")
    if joint_decision.get("decision") != "smart_500_joint_evidence_candidate":
        return _result(False, "joint_decision_not_positive_candidate")
    if joint_decision.get("standard_150_contract") != "unchanged_upstream_reference":
        return _result(False, "joint_decision_standard_150_contract_invalid")

    site_ids = _site_ids(joint_decision.get("site_ids"))
    if site_ids is None:
        return _result(False, "joint_site_population_invalid")
    smart_fingerprints = _smart_fingerprints(
        joint_decision.get("smart_500_population_fingerprints"), site_ids
    )
    if smart_fingerprints is None:
        return _result(False, "joint_smart_500_population_set_invalid")
    joint_evidence_fingerprint = _sha256(joint_decision.get("joint_evidence_fingerprint"))
    fix_corpus_fingerprint = _sha256(joint_decision.get("fix_corpus_fingerprint"))
    full_comparison_sites = _nonnegative_int(joint_decision.get("full_comparison_sites"))
    if (
        joint_evidence_fingerprint is None
        or fix_corpus_fingerprint is None
        or full_comparison_sites is None
        or full_comparison_sites <= 0
        or full_comparison_sites > len(site_ids)
    ):
        return _result(False, "joint_identity_or_full_comparison_count_invalid")

    if not isinstance(lineages_by_site, Mapping):
        return _result(False, "lineages_by_site_not_mapping")
    if tuple(sorted(lineages_by_site)) != site_ids:
        return _result(False, "lineage_site_population_mismatch")

    site_rows: list[dict[str, Any]] = []
    observed_full_comparison_sites = 0
    for site_id in site_ids:
        lineage = lineages_by_site.get(site_id)
        if not isinstance(lineage, Mapping):
            return _result(False, f"lineage_not_mapping:{site_id}")
        if lineage.get("version") != ADAPTIVE_MANIFEST_EVIDENCE_LINEAGE_VERSION:
            return _result(False, f"lineage_version_mismatch:{site_id}")
        if lineage.get("valid") is not True:
            return _result(False, f"lineage_invalid:{site_id}")
        if not _shadow_flags_valid(lineage):
            return _result(False, f"lineage_shadow_flags_invalid:{site_id}")
        if lineage.get("standard_150_preserved") is not True:
            return _result(False, f"lineage_standard_150_not_preserved:{site_id}")

        candidate_count = _nonnegative_int(lineage.get("candidate_count"))
        standard_pages = _nonnegative_int(lineage.get("standard_150_pages"))
        smart_pages = _nonnegative_int(lineage.get("smart_500_pages"))
        tail_pages = _nonnegative_int(lineage.get("blind_1000_pages"))
        if None in (candidate_count, standard_pages, smart_pages, tail_pages):
            return _result(False, f"lineage_population_geometry_invalid:{site_id}")
        assert candidate_count is not None
        assert standard_pages is not None
        assert smart_pages is not None
        assert tail_pages is not None
        if standard_pages != min(STANDARD_TARGET, candidate_count):
            return _result(False, f"lineage_standard_150_page_count_mismatch:{site_id}")
        if smart_pages != min(SMART_TARGET, candidate_count):
            return _result(False, f"lineage_smart_500_page_count_mismatch:{site_id}")
        if tail_pages != min(TAIL_TARGET, candidate_count):
            return _result(False, f"lineage_tail_1000_page_count_mismatch:{site_id}")
        if not (standard_pages <= smart_pages <= tail_pages):
            return _result(False, f"lineage_population_geometry_not_monotonic:{site_id}")

        checkpoints = _checkpoint_fingerprints(lineage.get("marginal_population_fingerprints"))
        targets = _selection_targets(lineage.get("selection_targets"))
        lineage_fingerprint = _sha256(lineage.get("lineage_fingerprint"))
        if checkpoints is None or targets is None or lineage_fingerprint is None:
            return _result(False, f"lineage_identity_invalid:{site_id}")
        if checkpoints[SMART_TARGET] != smart_fingerprints[site_id]:
            return _result(False, f"joint_smart_500_population_mismatch:{site_id}")

        expected_state = "full_blind_1000_reference" if candidate_count >= TAIL_TARGET else "inventory_limited"
        if lineage.get("comparison_state") != expected_state:
            return _result(False, f"lineage_comparison_state_mismatch:{site_id}")
        if expected_state == "full_blind_1000_reference":
            observed_full_comparison_sites += 1

        site_rows.append(
            {
                "site_id": site_id,
                "candidate_count": candidate_count,
                "selection_targets": targets,
                "standard_150_pages": standard_pages,
                "smart_500_pages": smart_pages,
                "tail_1000_pages": tail_pages,
                "standard_150_population_fingerprint": checkpoints[STANDARD_TARGET],
                "smart_500_population_fingerprint": checkpoints[SMART_TARGET],
                "tail_1000_population_fingerprint": checkpoints[TAIL_TARGET],
                "comparison_state": expected_state,
                "manifest_lineage_fingerprint": lineage_fingerprint,
            }
        )

    if observed_full_comparison_sites != full_comparison_sites:
        return _result(False, "full_comparison_site_count_mismatch")

    identity = {
        "joint_evidence_fingerprint": joint_evidence_fingerprint,
        "fix_corpus_fingerprint": fix_corpus_fingerprint,
        "site_ids": site_ids,
        "full_comparison_sites": full_comparison_sites,
        "sites": tuple(site_rows),
    }
    return _result(
        True,
        "joint_candidate_bound_to_exact_manifest_tranche_lineage",
        **identity,
        joint_manifest_lineage_fingerprint=_fingerprint_json(identity),
        standard_150_preserved=True,
        tranche_contract=(STANDARD_TARGET, SMART_TARGET, TAIL_TARGET),
    )
