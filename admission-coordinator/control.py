"""Pure global-barrier, cohort, snapshot and audit helpers.

The Firestore/HTTP layer lives in :mod:`main`.  Keeping validation and the
signed record shapes here makes the release boundary deterministic and testable
without credentials or a Firestore emulator.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

import admission


DRAIN_SNAPSHOT_VERSION = "admission_drain_snapshot_v1"
AUDIT_EVENT_VERSION = "admission_operator_audit_v1"
ACCEPTANCE_COHORT_VERSION = "admission_acceptance_cohort_v1"
RECONCILIATION_INVOCATION_VERSION = "admission_reconciliation_invocation_v1"

SNAPSHOT_LABEL = b"fixlist-admission-drain-snapshot-v1"
AUDIT_LABEL = b"fixlist-admission-operator-audit-v1"
COHORT_LABEL = b"fixlist-admission-acceptance-cohort-v1"

MAX_ACCEPTANCE_OWNERS = 100
MAX_ACCEPTANCE_TOTAL_CLAIMS = 500
MAX_ACCEPTANCE_LIFETIME_SECONDS = 14 * 24 * 60 * 60
MAX_SNAPSHOT_SAMPLE = 64
MAX_INTERNAL_OBLIGATIONS = 500
MIN_RECONCILIATION_LEASE_SECONDS = 30
MAX_RECONCILIATION_LEASE_SECONDS = 180

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,159}$")


class ControlError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _id(value: Any, code: str) -> str:
    text = str(value or "").strip()
    if not _ID_RE.fullmatch(text):
        raise ControlError(code)
    return text


def _text(value: Any, *, minimum: int, maximum: int, code: str) -> str:
    text = str(value or "").strip()
    if len(text) < minimum or len(text) > maximum:
        raise ControlError(code)
    return text


def _integer(value: Any, *, minimum: int, maximum: int, code: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ControlError(code) from None
    if number < minimum or number > maximum:
        raise ControlError(code)
    return number


def stable_serialize(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_record(root: str, label: bytes, value: dict[str, Any]) -> str:
    derived = hmac.new(root.encode("utf-8"), label, hashlib.sha256).digest()
    return hmac.new(derived, stable_serialize(value).encode("utf-8"), hashlib.sha256).hexdigest()


def verify_record(root: str, label: bytes, value: dict[str, Any], proof: str) -> bool:
    expected = sign_record(root, label, value)
    return hmac.compare_digest(str(proof or "").lower(), expected)


def validate_operator_context(payload: dict[str, Any]) -> dict[str, str]:
    reason = _text(payload.get("reason"), minimum=8, maximum=500, code="invalid_operator_reason")
    ticket = str(payload.get("change_ticket") or "").strip()
    if not _TICKET_RE.fullmatch(ticket):
        raise ControlError("invalid_change_ticket")
    return {"reason": reason, "change_ticket": ticket}


def require_intended_prior(control: dict[str, Any] | None, value: Any) -> dict[str, Any]:
    current = admission.normalized_control(control)
    intended = value if isinstance(value, dict) else {}
    mode = str(intended.get("mode") or "").strip().lower()
    try:
        generation = admission.normalize_barrier_generation(intended.get("generation"))
    except admission.AdmissionError as error:
        raise ControlError(error.code) from None
    if mode != current["mode"] or generation != current["generation"]:
        raise ControlError("barrier_intended_prior_mismatch")
    return current


def close_control(
    current: dict[str, Any],
    *,
    snapshot_id: str,
    operator_id: str,
    reason: str,
    change_ticket: str,
    now: int,
) -> dict[str, Any]:
    if current["mode"] == admission.BARRIER_CLOSED:
        raise ControlError("barrier_already_closed")
    return {
        **current,
        "mode": admission.BARRIER_CLOSED,
        "generation": int(current["generation"]) + 1,
        "current_snapshot_id": _id(snapshot_id, "invalid_snapshot_id"),
        "close_snapshot_id": _id(snapshot_id, "invalid_snapshot_id"),
        "closed_at": int(now),
        "closed_by": _id(operator_id, "invalid_operator_id"),
        "close_reason": reason,
        "close_change_ticket": change_ticket,
        "intended_prior_mode": current["mode"],
        "intended_prior_generation": int(current["generation"]),
        # A closed barrier never carries live acceptance authority. The
        # immutable cohort record and audit retain the prior definition.
        "acceptance": None,
    }


def is_exact_close_replay(
    current: dict[str, Any],
    intended_prior: Any,
    *,
    operator_id: str,
    reason: str,
    change_ticket: str,
) -> bool:
    """Recognize only a byte-equivalent logical retry of a committed close."""
    intended = intended_prior if isinstance(intended_prior, dict) else {}
    try:
        prior_generation = admission.normalize_barrier_generation(intended.get("generation"))
    except admission.AdmissionError:
        return False
    return bool(
        current.get("mode") == admission.BARRIER_CLOSED
        and str(intended.get("mode") or "").strip().lower()
        == str(current.get("intended_prior_mode") or "")
        and prior_generation == current.get("intended_prior_generation")
        and int(current.get("generation") or -1) == prior_generation + 1
        and str(current.get("closed_by") or "") == operator_id
        and str(current.get("close_reason") or "") == reason
        and str(current.get("close_change_ticket") or "") == change_ticket
        and bool(str(current.get("close_snapshot_id") or ""))
        and bool(str(current.get("close_audit_event_id") or ""))
    )


def open_control(
    current: dict[str, Any],
    *,
    snapshot_id: str,
    operator_id: str,
    reason: str,
    change_ticket: str,
    now: int,
) -> dict[str, Any]:
    if current["mode"] != admission.BARRIER_CLOSED:
        raise ControlError("barrier_not_closed")
    return {
        **current,
        "mode": admission.BARRIER_OPEN,
        "generation": int(current["generation"]) + 1,
        "current_snapshot_id": _id(snapshot_id, "invalid_snapshot_id"),
        "opened_at": int(now),
        "opened_by": _id(operator_id, "invalid_operator_id"),
        "open_reason": reason,
        "open_change_ticket": change_ticket,
        "intended_prior_mode": current["mode"],
        "intended_prior_generation": int(current["generation"]),
        "acceptance": None,
    }


def acceptance_definition(value: Any, *, now: int, operator_id: str) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    cohort_id = _id(source.get("cohort_id"), "invalid_acceptance_cohort_id")
    release_id = _id(source.get("release_id"), "invalid_acceptance_release_id")
    source_sha = str(source.get("source_sha") or "").strip().lower()
    if not _SHA_RE.fullmatch(source_sha):
        raise ControlError("invalid_acceptance_source_sha")
    owners_source = source.get("owner_user_ids")
    if not isinstance(owners_source, list):
        raise ControlError("invalid_acceptance_owner_allowlist")
    owners = sorted({_id(item, "invalid_acceptance_owner_id") for item in owners_source})
    if not owners or len(owners) != len(owners_source) or len(owners) > MAX_ACCEPTANCE_OWNERS:
        raise ControlError("invalid_acceptance_owner_allowlist")
    expires_at = _integer(
        source.get("expires_at"),
        minimum=int(now) + 1,
        maximum=int(now) + MAX_ACCEPTANCE_LIFETIME_SECONDS,
        code="invalid_acceptance_expiry",
    )
    total_budget = _integer(
        source.get("total_claim_budget"),
        minimum=1,
        maximum=MAX_ACCEPTANCE_TOTAL_CLAIMS,
        code="invalid_acceptance_total_budget",
    )
    per_owner_budget = _integer(
        source.get("per_owner_claim_budget"),
        minimum=1,
        maximum=total_budget,
        code="invalid_acceptance_owner_budget",
    )
    return {
        "version": ACCEPTANCE_COHORT_VERSION,
        "cohort_id": cohort_id,
        "release_id": release_id,
        "source_sha": source_sha,
        "owner_allowlist": owners,
        "expires_at": expires_at,
        "total_claim_budget": total_budget,
        "per_owner_claim_budget": per_owner_budget,
        "created_at": int(now),
        "created_by": _id(operator_id, "invalid_operator_id"),
    }


def acceptance_control(
    current: dict[str, Any],
    definition: dict[str, Any],
    *,
    snapshot_id: str,
    operator_id: str,
    reason: str,
    change_ticket: str,
    now: int,
) -> dict[str, Any]:
    if current["mode"] != admission.BARRIER_CLOSED:
        raise ControlError("barrier_not_closed")
    acceptance = {
        **definition,
        "total_claims_used": 0,
        "owner_claims_used": {},
    }
    return {
        **current,
        "mode": admission.BARRIER_ACCEPTANCE_ONLY,
        "generation": int(current["generation"]) + 1,
        "current_snapshot_id": _id(snapshot_id, "invalid_snapshot_id"),
        "acceptance_enabled_at": int(now),
        "acceptance_enabled_by": _id(operator_id, "invalid_operator_id"),
        "acceptance_reason": reason,
        "acceptance_change_ticket": change_ticket,
        "intended_prior_mode": current["mode"],
        "intended_prior_generation": int(current["generation"]),
        "acceptance": acceptance,
    }


def _admission_obligation(document: dict[str, Any]) -> dict[str, Any] | None:
    state = str(document.get("state") or "").strip().lower()
    if state not in {admission.STATE_CLAIMED, admission.STATE_BOUND}:
        return None
    return {
        "owner_user_id": str(document.get("owner_user_id") or ""),
        "request_id": str(document.get("request_id") or ""),
        "scan_id": str(document.get("scan_id") or ""),
        "state": state,
        "barrier_generation": admission.normalize_barrier_generation(document.get("barrier_generation", 0)),
        "claim_sequence": admission.normalize_claim_sequence(document.get("claim_sequence", 0)),
        "claimed_at": document.get("claimed_at"),
        "lease_expires_at": document.get("lease_expires_at"),
        "admission_mode": str(document.get("admission_mode") or admission.BARRIER_OPEN),
        "acceptance_cohort_id": str(document.get("acceptance_cohort_id") or ""),
        "acceptance_release_id": str(document.get("acceptance_release_id") or ""),
        "acceptance_source_sha": str(document.get("acceptance_source_sha") or ""),
    }


def _live_reconciliation(document: dict[str, Any], *, now: int) -> dict[str, Any] | None:
    if str(document.get("state") or "") != "live":
        return None
    try:
        lease_expires_at = int(document.get("lease_expires_at") or 0)
    except (TypeError, ValueError):
        return None
    if lease_expires_at <= int(now):
        return None
    return {
        "invocation_id": str(document.get("invocation_id") or ""),
        "source_sha": str(document.get("source_sha") or ""),
        "started_at": document.get("started_at"),
        "lease_expires_at": lease_expires_at,
        "barrier_generation": admission.normalize_barrier_generation(document.get("barrier_generation", 0)),
        "reconciliation_sequence": admission.normalize_claim_sequence(
            document.get("reconciliation_sequence", 0)
        ),
    }


def build_snapshot(
    *,
    snapshot_id: str,
    control: dict[str, Any],
    admission_documents: list[dict[str, Any]],
    reconciliation_documents: list[dict[str, Any]],
    now: int,
    operator_id: str,
    reason: str,
    change_ticket: str,
    signing_root: str,
    boundary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obligations = [item for item in (_admission_obligation(doc) for doc in admission_documents) if item]
    obligations.sort(key=lambda item: (int(item["claim_sequence"]), item["owner_user_id"], item["request_id"]))
    live = [item for item in (_live_reconciliation(doc, now=now) for doc in reconciliation_documents) if item]
    live.sort(key=lambda item: item["invocation_id"])
    claimed_active = 0
    claimed_expired = 0
    bound = 0
    for item in obligations:
        if item["state"] == admission.STATE_BOUND:
            bound += 1
        elif int(item.get("lease_expires_at") or 0) > int(now):
            claimed_active += 1
        else:
            claimed_expired += 1
    counts = {
        "claimed_active": claimed_active,
        "claimed_expired": claimed_expired,
        "bound": bound,
        "live_reconciliation": len(live),
        "total_obligations": len(obligations),
    }
    if len(obligations) > MAX_INTERNAL_OBLIGATIONS or len(live) > MAX_INTERNAL_OBLIGATIONS:
        # A partial snapshot would violate the barrier invariant. Refuse the
        # transition instead of silently omitting an obligation.
        raise ControlError("drain_snapshot_capacity_exceeded")
    obligations_digest = hashlib.sha256(stable_serialize(obligations).encode("utf-8")).hexdigest()
    reconciliation_digest = hashlib.sha256(stable_serialize(live).encode("utf-8")).hexdigest()
    unsigned = {
        "version": DRAIN_SNAPSHOT_VERSION,
        "snapshot_id": _id(snapshot_id, "invalid_snapshot_id"),
        "created_at": int(now),
        "operator_id": _id(operator_id, "invalid_operator_id"),
        "reason": reason,
        "change_ticket": change_ticket,
        "barrier": {
            "mode": control["mode"],
            "generation": int(control["generation"]),
            "claim_sequence": int(control["claim_sequence"]),
            "reconciliation_sequence": admission.normalize_claim_sequence(
                control.get("reconciliation_sequence", 0)
            ),
            "current_snapshot_id": str(control.get("current_snapshot_id") or ""),
        },
        "boundary": boundary or {},
        "admission_obligations_digest": obligations_digest,
        "live_reconciliation_digest": reconciliation_digest,
        "admission_obligation_sample": obligations[:MAX_SNAPSHOT_SAMPLE],
        "live_reconciliation_sample": live[:MAX_SNAPSHOT_SAMPLE],
        "counts": counts,
        # An expired, never-bound claim is retained as immutable diagnostic
        # evidence but no longer owns admission and cannot be executing work.
        # Base44 reconciliation records satisfied_unbound when a matching row
        # exists. The semantic cutover blockers are therefore bound scans,
        # live unbound claims, and live reconciliation invocations.
        "drain_ready": (
            counts["bound"] == 0
            and counts["claimed_active"] == 0
            and counts["live_reconciliation"] == 0
        ),
    }
    # The signed/public manifest stays bounded. The full lists are persisted in
    # the immutable Firestore record under explicitly internal keys so the
    # operator can later prove each pre-boundary obligation from the digest
    # without spilling an unbounded identity list into CI logs.
    return {
        **unsigned,
        "proof": sign_record(signing_root, SNAPSHOT_LABEL, unsigned),
        "_internal_admission_obligations": obligations,
        "_internal_live_reconciliation_invocations": live,
    }


def public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in snapshot.items() if not key.startswith("_internal_")}


def build_audit_event(
    *,
    event_id: str,
    operation: str,
    operator_id: str,
    reason: str,
    change_ticket: str,
    now: int,
    prior: dict[str, Any],
    result: dict[str, Any],
    snapshot_id: str,
    signing_root: str,
) -> dict[str, Any]:
    unsigned = {
        "version": AUDIT_EVENT_VERSION,
        "event_id": _id(event_id, "invalid_audit_event_id"),
        "operation": _id(operation.replace("-", "_"), "invalid_audit_operation"),
        "operator_id": _id(operator_id, "invalid_operator_id"),
        "reason": reason,
        "change_ticket": change_ticket,
        "created_at": int(now),
        "intended_prior": {
            "mode": prior["mode"],
            "generation": int(prior["generation"]),
        },
        "result": {
            "mode": result["mode"],
            "generation": int(result["generation"]),
        },
        "snapshot_id": _id(snapshot_id, "invalid_snapshot_id"),
    }
    return {**unsigned, "proof": sign_record(signing_root, AUDIT_LABEL, unsigned)}


def signed_acceptance_definition(definition: dict[str, Any], signing_root: str) -> dict[str, Any]:
    return {**definition, "proof": sign_record(signing_root, COHORT_LABEL, definition)}


def reconciliation_lease_seconds(value: Any) -> int:
    return _integer(
        value,
        minimum=MIN_RECONCILIATION_LEASE_SECONDS,
        maximum=MAX_RECONCILIATION_LEASE_SECONDS,
        code="invalid_reconciliation_lease_seconds",
    )


def reconciliation_invocation_id(value: Any) -> str:
    return _id(value, "invalid_reconciliation_invocation_id")


def _source_sha(value: Any, code: str = "invalid_reconciliation_source_sha") -> str:
    source_sha = str(value or "").strip().lower()
    if not _SHA_RE.fullmatch(source_sha):
        raise ControlError(code)
    return source_sha


def public_reconciliation_invocation(document: dict[str, Any] | None) -> dict[str, Any]:
    """Return the bounded, non-secret reconciliation identity contract."""
    source = document if isinstance(document, dict) else {}
    return {
        "version": str(source.get("version") or RECONCILIATION_INVOCATION_VERSION),
        "invocation_id": str(source.get("invocation_id") or ""),
        "source_sha": str(source.get("source_sha") or ""),
        "state": str(source.get("state") or ""),
        "started_at": source.get("started_at"),
        "lease_expires_at": source.get("lease_expires_at"),
        "barrier_generation": admission.normalize_barrier_generation(
            source.get("barrier_generation", 0)
        ),
        "reconciliation_sequence": admission.normalize_claim_sequence(
            source.get("reconciliation_sequence", 0)
        ),
        "finished_at": source.get("finished_at"),
        "outcome": str(source.get("outcome") or ""),
    }


def decide_reconciliation_start(
    document: dict[str, Any] | None,
    barrier: dict[str, Any] | None,
    *,
    invocation_id: Any,
    source_sha: Any,
    lease_seconds: Any,
    now: int,
) -> dict[str, Any]:
    """Register a bounded live reconciler against the same barrier boundary.

    A fresh invocation advances ``reconciliation_sequence`` on the global
    control document. Barrier close writes that same document, so Firestore
    serializes the two operations. Closing the claim barrier must not stop
    reconciliation: operators close claims first and keep the drain plane live
    until all pre-boundary obligations are settled.
    """
    invocation = reconciliation_invocation_id(invocation_id)
    source = _source_sha(source_sha)
    lease = reconciliation_lease_seconds(lease_seconds)
    moment = int(now)
    current = admission.normalized_control(barrier)

    if isinstance(document, dict) and document:
        existing_invocation = str(document.get("invocation_id") or "")
        existing_source = str(document.get("source_sha") or "")
        if existing_invocation != invocation or existing_source != source:
            return {
                "outcome": None,
                "error": "reconciliation_identity_conflict",
                "document": document,
            }
        state = str(document.get("state") or "")
        if state == "finished":
            return {
                "outcome": "already_finished",
                "document": document,
                "invocation": public_reconciliation_invocation(document),
            }
        if state == "live" and int(document.get("lease_expires_at") or 0) > moment:
            return {
                "outcome": "already_started",
                "document": document,
                "invocation": public_reconciliation_invocation(document),
            }
        return {
            "outcome": None,
            "error": "reconciliation_invocation_expired",
            "document": document,
        }

    reconciliation_sequence = admission.normalize_claim_sequence(
        current.get("reconciliation_sequence", 0)
    ) + 1
    control_write = {
        **current,
        "reconciliation_sequence": reconciliation_sequence,
    }
    write = {
        "version": RECONCILIATION_INVOCATION_VERSION,
        "invocation_id": invocation,
        "source_sha": source,
        "state": "live",
        "started_at": moment,
        "lease_expires_at": moment + lease,
        "barrier_generation": int(current["generation"]),
        "reconciliation_sequence": reconciliation_sequence,
        "finished_at": None,
        "outcome": "",
    }
    return {
        "outcome": "started",
        "write": write,
        "control_write": control_write,
        "document": write,
        "invocation": public_reconciliation_invocation(write),
    }


def decide_reconciliation_finish(
    document: dict[str, Any] | None,
    *,
    invocation_id: Any,
    source_sha: Any,
    outcome: Any,
    now: int,
) -> dict[str, Any]:
    """Finish one exact invocation; retries are identity-safe and idempotent."""
    invocation = reconciliation_invocation_id(invocation_id)
    source = _source_sha(source_sha)
    result = str(outcome or "").strip()
    if result not in {"success", "retryable_failure"}:
        raise ControlError("invalid_reconciliation_outcome")
    if not isinstance(document, dict) or not document:
        return {
            "outcome": None,
            "error": "reconciliation_invocation_not_found",
            "document": None,
        }
    if (
        str(document.get("invocation_id") or "") != invocation
        or str(document.get("source_sha") or "") != source
    ):
        return {
            "outcome": None,
            "error": "reconciliation_identity_conflict",
            "document": document,
        }
    if str(document.get("state") or "") == "finished":
        if str(document.get("outcome") or "") != result:
            return {
                "outcome": None,
                "error": "reconciliation_outcome_conflict",
                "document": document,
            }
        return {
            "outcome": "already_finished",
            "document": document,
            "invocation": public_reconciliation_invocation(document),
        }
    if str(document.get("state") or "") != "live":
        return {
            "outcome": None,
            "error": "reconciliation_state_conflict",
            "document": document,
        }
    moment = int(now)
    write = {
        **document,
        "state": "finished",
        "finished_at": moment,
        "lease_expires_at": moment,
        "outcome": result,
    }
    return {
        "outcome": "finished",
        "write": write,
        "document": write,
        "invocation": public_reconciliation_invocation(write),
    }
