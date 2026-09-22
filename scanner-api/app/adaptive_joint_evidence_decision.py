"""Shadow-only joint decision for adaptive discovery and Fix benchmark evidence.

The adaptive crawl experiment decision answers whether evidence beyond the unchanged
Standard 150 is valuable and whether Smart 500 is efficient versus a blind 1,000-page
reference. The Fix benchmark acceptance decision independently answers whether Smart
500 preserves enough opaque Fix evidence. This helper binds those two decision
envelopes to the exact same site and Smart-500 populations before allowing a joint
engineering candidate.

It is deliberately pure. It performs no crawling, ranking, persistence, authority,
customer projection, budget mutation, admission, release, deployment, or network work.
A positive result is shadow experiment evidence only and never authorizes production.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

ADAPTIVE_CRAWL_EXPERIMENT_DECISION_VERSION = "adaptive_crawl_experiment_decision_v1"
ADAPTIVE_FIX_BENCHMARK_ACCEPTANCE_VERSION = "adaptive_fix_benchmark_acceptance_v1"
ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION = "adaptive_joint_evidence_decision_v1"

_EXPERIMENT_DECISIONS = {
    "smart_500_experiment_candidate",
    "blind_1000_reference_retained",
    "standard_150_reference_retained",
    "insufficient_evidence",
}
_FIX_DECISIONS = {
    "smart_500_fix_evidence_candidate",
    "blind_1000_fix_reference_retained",
    "insufficient_evidence",
}


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, set):
        return sorted(_canonical(item) for item in value)
    return value


def _fingerprint_json(value: Any, *, domain: str) -> str:
    digest = hashlib.sha256()
    digest.update(domain.encode("utf-8"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            _canonical(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return digest.hexdigest()


def _result(decision: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION,
        "decision": decision,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
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


def _site_ids(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    ids = tuple(value)
    if (
        not ids
        or any(not isinstance(site_id, str) or not site_id or site_id.strip() != site_id for site_id in ids)
        or len(set(ids)) != len(ids)
        or ids != tuple(sorted(ids))
    ):
        return None
    return ids


def _sha256_hex(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value


def _experiment_smart_populations(
    value: Any, expected_site_ids: tuple[str, ...]
) -> tuple[tuple[str, str], ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    rows = tuple(value)
    if len(rows) != len(expected_site_ids):
        return None
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence):
            return None
        parts = tuple(row)
        if len(parts) != 2:
            return None
        site_id, smart_fingerprint = parts
        if (
            not isinstance(site_id, str)
            or site_id in seen
            or _sha256_hex(smart_fingerprint) is None
        ):
            return None
        seen.add(site_id)
        normalized.append((site_id, smart_fingerprint))
    normalized.sort(key=lambda item: item[0])
    result = tuple(normalized)
    if tuple(site_id for site_id, _ in result) != expected_site_ids:
        return None
    return result


def _fix_smart_populations(
    value: Any, expected_site_ids: tuple[str, ...]
) -> tuple[tuple[str, str], ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    rows = tuple(value)
    if len(rows) != len(expected_site_ids):
        return None
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence):
            return None
        parts = tuple(row)
        if len(parts) != 4:
            return None
        site_id, smart_fingerprint, blind_fingerprint, binding_fingerprint = parts
        if (
            not isinstance(site_id, str)
            or site_id in seen
            or _sha256_hex(smart_fingerprint) is None
            or _sha256_hex(blind_fingerprint) is None
            or _sha256_hex(binding_fingerprint) is None
        ):
            return None
        seen.add(site_id)
        normalized.append((site_id, smart_fingerprint))
    normalized.sort(key=lambda item: item[0])
    result = tuple(normalized)
    if tuple(site_id for site_id, _ in result) != expected_site_ids:
        return None
    return result


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def evaluate_joint_adaptive_evidence(
    experiment_decision: Mapping[str, Any] | Any,
    fix_decision: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Join the two Lane-A acceptance families without authorizing production.

    Positive evidence is accepted only when both upstream decisions are positive and
    their exact sorted site identities and Smart-500 population fingerprints match.
    This prevents a discovery benchmark from one same-count population being combined
    with Fix evidence from another. Conservative upstream outcomes propagate without
    upgrading authority.
    """
    if not isinstance(experiment_decision, Mapping):
        return _result("insufficient_evidence", "experiment_decision_not_mapping")
    if not isinstance(fix_decision, Mapping):
        return _result("insufficient_evidence", "fix_decision_not_mapping")
    if experiment_decision.get("version") != ADAPTIVE_CRAWL_EXPERIMENT_DECISION_VERSION:
        return _result("insufficient_evidence", "experiment_decision_version_mismatch")
    if fix_decision.get("version") != ADAPTIVE_FIX_BENCHMARK_ACCEPTANCE_VERSION:
        return _result("insufficient_evidence", "fix_decision_version_mismatch")
    if not _shadow_flags_valid(experiment_decision):
        return _result("insufficient_evidence", "experiment_decision_shadow_flags_invalid")
    if not _shadow_flags_valid(fix_decision):
        return _result("insufficient_evidence", "fix_decision_shadow_flags_invalid")

    experiment_outcome = experiment_decision.get("decision")
    fix_outcome = fix_decision.get("decision")
    if experiment_outcome not in _EXPERIMENT_DECISIONS:
        return _result("insufficient_evidence", "experiment_decision_unknown")
    if fix_outcome not in _FIX_DECISIONS:
        return _result("insufficient_evidence", "fix_decision_unknown")

    if experiment_outcome == "insufficient_evidence":
        return _result(
            "insufficient_evidence",
            "experiment_evidence_insufficient",
            experiment_reason=experiment_decision.get("reason"),
        )
    if fix_outcome == "insufficient_evidence":
        return _result(
            "insufficient_evidence",
            "fix_evidence_insufficient",
            fix_reason=fix_decision.get("reason"),
        )
    if experiment_outcome == "standard_150_reference_retained":
        return _result(
            "standard_150_joint_reference_retained",
            "experiment_did_not_justify_expansion_beyond_standard_150",
            experiment_reason=experiment_decision.get("reason"),
            fix_decision=fix_outcome,
        )
    if experiment_outcome == "blind_1000_reference_retained":
        return _result(
            "blind_1000_joint_reference_retained",
            "discovery_evidence_retained_blind_1000_reference",
            experiment_reason=experiment_decision.get("reason"),
            fix_decision=fix_outcome,
        )
    if fix_outcome == "blind_1000_fix_reference_retained":
        return _result(
            "blind_1000_joint_reference_retained",
            "fix_evidence_retained_blind_1000_reference",
            experiment_decision=experiment_outcome,
            fix_reason=fix_decision.get("reason"),
        )

    # Both evidence families now claim a Smart-500 engineering candidate. Bind them.
    experiment_site_ids = _site_ids(experiment_decision.get("site_ids"))
    fix_site_ids = _site_ids(fix_decision.get("site_ids"))
    if experiment_site_ids is None or fix_site_ids is None:
        return _result("insufficient_evidence", "joint_site_population_invalid")
    if experiment_site_ids != fix_site_ids:
        return _result("insufficient_evidence", "joint_site_population_mismatch")

    experiment_populations = _experiment_smart_populations(
        experiment_decision.get("smart_500_population_fingerprints"), experiment_site_ids
    )
    fix_populations = _fix_smart_populations(
        fix_decision.get("population_fingerprints"), fix_site_ids
    )
    if experiment_populations is None or fix_populations is None:
        return _result("insufficient_evidence", "joint_population_fingerprint_set_invalid")
    if experiment_populations != fix_populations:
        return _result("insufficient_evidence", "joint_smart_500_population_mismatch")

    experiment_full_sites = _positive_int(experiment_decision.get("full_comparison_sites"))
    fix_full_sites = _positive_int(fix_decision.get("full_comparison_sites"))
    if experiment_full_sites is None or fix_full_sites is None:
        return _result("insufficient_evidence", "joint_full_comparison_count_invalid")
    if experiment_full_sites != fix_full_sites or experiment_full_sites > len(experiment_site_ids):
        return _result("insufficient_evidence", "joint_full_comparison_count_mismatch")

    fix_corpus_fingerprint = _sha256_hex(fix_decision.get("corpus_fingerprint"))
    if fix_corpus_fingerprint is None:
        return _result("insufficient_evidence", "fix_corpus_fingerprint_invalid")

    identity = {
        "experiment_version": ADAPTIVE_CRAWL_EXPERIMENT_DECISION_VERSION,
        "fix_version": ADAPTIVE_FIX_BENCHMARK_ACCEPTANCE_VERSION,
        "experiment_decision": experiment_outcome,
        "fix_decision": fix_outcome,
        "site_ids": experiment_site_ids,
        "smart_500_population_fingerprints": experiment_populations,
        "full_comparison_sites": experiment_full_sites,
        "fix_corpus_fingerprint": fix_corpus_fingerprint,
    }
    return _result(
        "smart_500_joint_evidence_candidate",
        "discovery_and_fix_evidence_agree_on_exact_smart_500_population",
        site_ids=experiment_site_ids,
        smart_500_population_fingerprints=experiment_populations,
        full_comparison_sites=experiment_full_sites,
        fix_corpus_fingerprint=fix_corpus_fingerprint,
        joint_evidence_fingerprint=_fingerprint_json(
            identity, domain=ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION
        ),
        standard_150_contract="unchanged_upstream_reference",
    )
