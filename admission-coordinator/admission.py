"""Pure admission-decision logic for the FixList scan coordinator.

Nothing in this module performs I/O. Every function takes the current
coordinator document (or None) plus a request, and returns a decision the
caller applies inside a real Firestore transaction. Keeping the state machine
free of I/O is what makes contention, expiry and partial-failure replay
testable without a Firestore emulator.

The coordinator document is deliberately small. It carries only the metadata
needed to decide who may start a scan. Scan evidence, review output, HMAC
authority proofs, payment state and customer content never enter this
document -- those live in Base44 behind the existing authority seal.
"""

from __future__ import annotations

import re
from typing import Any

# Lifecycle of a coordinator document.
STATE_CLAIMED = "claimed"
STATE_BOUND = "bound"
STATE_RELEASED = "released"

ACTIVE_STATES = frozenset({STATE_CLAIMED, STATE_BOUND})

# A scan reaches exactly one of these, and only the durable worker or the
# server-side watchdog may declare it. The browser has no vote.
TERMINAL_STATUSES = frozenset({"complete", "limited", "failed", "cancelled"})

# Outcomes returned to the caller. These are a closed set so the Base44 client
# can branch on them without string-matching free text.
OUTCOME_CLAIMED = "claimed"
OUTCOME_REPLAYED = "replayed"
OUTCOME_BUSY = "busy"
OUTCOME_BOUND = "bound"
OUTCOME_ALREADY_BOUND = "already_bound"
OUTCOME_RELEASED = "released"
OUTCOME_ALREADY_RELEASED = "already_released"

# Fail-closed error codes.
ERROR_REQUEST_CONFLICT = "request_conflict"
ERROR_SCAN_IDENTITY_CONFLICT = "scan_identity_conflict"
ERROR_INVALID_CLAIM_TOKEN = "invalid_claim_token"
ERROR_CLAIM_EXPIRED = "claim_expired"
ERROR_CLAIM_NOT_FOUND = "claim_not_found"
ERROR_NOT_TERMINAL = "not_terminal_status"
ERROR_SCAN_NOT_BOUND = "scan_not_bound"

DEFAULT_LEASE_SECONDS = 2400
MIN_LEASE_SECONDS = 60
MAX_LEASE_SECONDS = 3600

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FINGERPRINT_MAX = 512


class AdmissionError(ValueError):
    """Raised for structurally invalid admission input.

    Carries a stable machine code so the HTTP layer never has to interpret a
    message string.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require_id(value: Any, code: str) -> str:
    text = str(value or "").strip()
    if not _ID_RE.fullmatch(text):
        raise AdmissionError(code)
    return text


def _require_fingerprint(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > _FINGERPRINT_MAX:
        raise AdmissionError("invalid_request_fingerprint")
    return text


def normalize_lease_seconds(value: Any) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LEASE_SECONDS
    if seconds < MIN_LEASE_SECONDS or seconds > MAX_LEASE_SECONDS:
        return DEFAULT_LEASE_SECONDS
    return seconds


def is_lease_active(document: dict[str, Any] | None, now: int) -> bool:
    """A lease is active only while its state is live AND it has not expired.

    Both halves matter. A released document is never active regardless of its
    expiry, and a claimed document past its expiry is reclaimable even though
    nothing explicitly released it -- that is what lets a vanished worker's
    admission be taken over instead of wedging the owner forever.
    """
    if not isinstance(document, dict):
        return False
    if str(document.get("state") or "") not in ACTIVE_STATES:
        return False
    try:
        expires_at = int(document.get("lease_expires_at") or 0)
    except (TypeError, ValueError):
        return False
    return expires_at > int(now)


def decide_claim(
    document: dict[str, Any] | None,
    *,
    owner_user_id: str,
    request_id: str,
    request_fingerprint: str,
    claim_token: str,
    now: int,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    """Decide whether this caller wins admission.

    Returns a decision dict. When ``write`` is present the caller must persist
    it as the new document inside the same transaction that read ``document``.
    When ``error`` is present nothing is written and the request fails closed.
    """
    owner = _require_id(owner_user_id, "invalid_owner_user_id")
    request = _require_id(request_id, "invalid_request_id")
    token = _require_id(claim_token, "invalid_claim_token_format")
    fingerprint = _require_fingerprint(request_fingerprint)
    lease = normalize_lease_seconds(lease_seconds)
    moment = int(now)

    fresh = {
        "owner_user_id": owner,
        "request_id": request,
        "request_fingerprint": fingerprint,
        "claim_token": token,
        "scan_id": "",
        "state": STATE_CLAIMED,
        "claimed_at": moment,
        "lease_expires_at": moment + lease,
        "released_at": None,
        "terminal_status": "",
    }

    # Rule A -- nothing holds admission: no document, already released, or the
    # previous lease expired without a terminal result.
    if not is_lease_active(document, moment):
        return {"outcome": OUTCOME_CLAIMED, "write": fresh, "document": fresh}

    assert isinstance(document, dict)
    held_request = str(document.get("request_id") or "")
    held_fingerprint = str(document.get("request_fingerprint") or "")

    # Rule D -- a different request is mid-flight. Create nothing, tell the
    # caller to retry. This is the cross-tab case.
    if held_request != request:
        return {
            "outcome": OUTCOME_BUSY,
            "retry_after_seconds": max(1, int(document.get("lease_expires_at") or moment) - moment),
            "document": document,
        }

    # Rule C -- same request id, different fingerprint. The request key has been
    # reused for different work; refusing is the only safe answer.
    if held_fingerprint != fingerprint:
        return {"outcome": None, "error": ERROR_REQUEST_CONFLICT, "document": document}

    # Rule B -- exact same request replayed. Hand back the existing claim so a
    # retried call is idempotent, including the bound ScanRun when there is one.
    return {
        "outcome": OUTCOME_REPLAYED,
        "document": document,
        "claim_token": str(document.get("claim_token") or ""),
        "scan_id": str(document.get("scan_id") or ""),
    }


def decide_bind(
    document: dict[str, Any] | None,
    *,
    request_id: str,
    claim_token: str,
    scan_id: str,
    now: int,
) -> dict[str, Any]:
    """Bind the canonical server-created ScanRun id to a winning claim.

    This is the second half of the partial-failure fix: admission is won
    first, the ScanRun is created second, and the id is written back here. A
    caller that loses the create response retries and lands on
    ``already_bound`` instead of creating a second row.
    """
    request = _require_id(request_id, "invalid_request_id")
    token = _require_id(claim_token, "invalid_claim_token_format")
    scan = _require_id(scan_id, "invalid_scan_id")
    moment = int(now)

    if not isinstance(document, dict) or not document:
        return {"outcome": None, "error": ERROR_CLAIM_NOT_FOUND, "document": None}

    if str(document.get("request_id") or "") != request:
        return {"outcome": None, "error": ERROR_REQUEST_CONFLICT, "document": document}

    # Compared before expiry so a caller holding the wrong token can never
    # learn anything from the difference between "expired" and "not yours".
    if str(document.get("claim_token") or "") != token:
        return {"outcome": None, "error": ERROR_INVALID_CLAIM_TOKEN, "document": document}

    if not is_lease_active(document, moment):
        return {"outcome": None, "error": ERROR_CLAIM_EXPIRED, "document": document}

    bound = str(document.get("scan_id") or "")

    if bound == scan:
        return {"outcome": OUTCOME_ALREADY_BOUND, "document": document, "scan_id": scan}

    if bound:
        return {"outcome": None, "error": ERROR_SCAN_IDENTITY_CONFLICT, "document": document}

    write = {**document, "scan_id": scan, "state": STATE_BOUND}
    return {"outcome": OUTCOME_BOUND, "write": write, "document": write, "scan_id": scan}


def decide_release(
    document: dict[str, Any] | None,
    *,
    scan_id: str,
    terminal_status: str,
    now: int,
) -> dict[str, Any]:
    """Release admission once a scan reaches a terminal state.

    Deliberately does NOT require the claim token. The releaser is the durable
    worker or the server watchdog, which knows the canonical scan id but was
    never handed the admission token. Matching on the bound scan id is the
    authority check: a caller that cannot name the bound scan cannot release it.
    """
    scan = _require_id(scan_id, "invalid_scan_id")
    status = str(terminal_status or "").strip().lower()
    moment = int(now)

    if status not in TERMINAL_STATUSES:
        return {"outcome": None, "error": ERROR_NOT_TERMINAL, "document": document}

    if not isinstance(document, dict) or not document:
        return {"outcome": None, "error": ERROR_CLAIM_NOT_FOUND, "document": None}

    bound = str(document.get("scan_id") or "")

    if not bound:
        return {"outcome": None, "error": ERROR_SCAN_NOT_BOUND, "document": document}

    if bound != scan:
        # Another scan holds admission. Releasing here would hand the owner's
        # slot away on behalf of a run that does not own it.
        return {"outcome": None, "error": ERROR_SCAN_IDENTITY_CONFLICT, "document": document}

    if str(document.get("state") or "") == STATE_RELEASED:
        return {"outcome": OUTCOME_ALREADY_RELEASED, "document": document}

    write = {
        **document,
        "state": STATE_RELEASED,
        "released_at": moment,
        "terminal_status": status,
        # Expiring the lease in the same write means a released document is
        # inactive under both halves of is_lease_active, so the next admission
        # succeeds immediately rather than waiting out the original lease.
        "lease_expires_at": moment,
    }
    return {"outcome": OUTCOME_RELEASED, "write": write, "document": write}


def public_view(document: dict[str, Any] | None) -> dict[str, Any]:
    """Project a document down to what a caller is allowed to see.

    The claim token is a bearer credential for the bind call, so it is never
    echoed back by the status surface -- only the claim response that minted it
    returns it.
    """
    if not isinstance(document, dict) or not document:
        return {"state": "", "scan_id": "", "request_id": ""}
    return {
        "state": str(document.get("state") or ""),
        "scan_id": str(document.get("scan_id") or ""),
        "request_id": str(document.get("request_id") or ""),
        "claimed_at": document.get("claimed_at"),
        "lease_expires_at": document.get("lease_expires_at"),
        "released_at": document.get("released_at"),
        "terminal_status": str(document.get("terminal_status") or ""),
    }
