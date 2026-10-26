"""Behavioral proof of separate Extended 500 owner slot, replay tombstone.

No Firestore emulator, Cloud Tasks credentials, or production writes needed.
Service adapter is tested separately; Firestore transaction is the atomic unit.
"""
import importlib.util
from pathlib import Path
import pytest

CORE = Path(__file__).resolve().parents[2] / "extended500-admission" / "core.py"
spec = importlib.util.spec_from_file_location("extended500_atomic_core", CORE)
core = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(core)
QUEUE = "projects/fixlist-test/locations/us-central1/queues/extended500-test"


def grant(owner="owner-one", request="request-one", attempt=1):
    return {
        "version": core.ENTITLEMENT_VERSION, "plan_id": core.PLAN,
        "scan_mode": core.MODE, "entitlement_state": "active_paid",
        "owner_user_id": owner, "scan_id": f"scan-{request}",
        "project_id": "project-one", "request_id": request,
        "idempotency_key": f"idem-{request}", "access_id": "access-500",
        "attempt_count": attempt,
    }


def reserve(entitlement, slot=None, receipt=None):
    return core.decide_reservation(slot, receipt, entitlement, QUEUE, issued_at=1000)


def test_owner_slot_and_request_receipt_atomic_writes_and_exact_replay():
    entitlement = grant()
    fresh = reserve(entitlement)
    assert fresh["outcome"] == "reserved"
    assert fresh["slot_write"]["receipt_id"] == fresh["receipt_write"]["receipt_id"]
    assert fresh["receipt_write"]["task_name"] == fresh["task_name"]
    assert fresh["slot_write"]["state"] == "reserved"
    assert "access_id" not in fresh["slot_write"]
    assert "entitlement" not in fresh["receipt_write"]
    assert "proof" not in fresh["receipt_write"]
    replay = reserve(entitlement, fresh["slot_write"], fresh["receipt_write"])
    assert replay["outcome"] == "replayed"
    assert replay["task_name"] == fresh["task_name"]
    assert "slot_write" not in replay and "receipt_write" not in replay


def test_different_request_or_attempt_cannot_claim_same_owner_slot():
    first = reserve(grant())
    with pytest.raises(core.AdmissionRefused, match="owner_slot_busy"):
        reserve(grant(request="next-request"), first["slot_write"])
    with pytest.raises(core.AdmissionRefused, match="owner_slot_busy"):
        reserve(grant(attempt=2), first["slot_write"])
    # Reusing request_id with changed attempt/scan ID is never a replay.
    with pytest.raises(core.AdmissionRefused, match="request_replay_conflict"):
        reserve(grant(attempt=2), first["slot_write"], first["receipt_write"])


def test_unknown_dispatch_keeps_reservation_and_replay_uses_same_name():
    original = reserve(grant())
    state = core.decide_dispatch_state(
        original["slot_write"], original["receipt_write"], state="dispatch_unknown",
    )
    assert state["outcome"] == "updated"
    assert state["slot_write"]["state"] == "dispatch_unknown"
    replay = reserve(grant(), state["slot_write"], state["receipt_write"])
    assert replay["task_name"] == original["task_name"]
    confirmed = core.decide_dispatch_state(state["slot_write"], state["receipt_write"], state="enqueued")
    assert confirmed["slot_write"]["state"] == "enqueued"
    late_failure = core.decide_dispatch_state(confirmed["slot_write"], confirmed["receipt_write"], state="dispatch_unknown")
    assert late_failure["outcome"] == "unchanged"


def test_release_requires_verified_exact_terminal_and_durable_tombstone():
    original = reserve(grant())
    request = core.canonical_request(grant())
    for status, verified in (("running", True), ("complete", False), ("queued", True)):
        with pytest.raises(core.AdmissionRefused, match="verified_terminal_required"):
            core.decide_release(
                original["slot_write"], original["receipt_write"], request,
                terminal_status=status, verified_terminal=verified, released_at=2000,
            )
    outcome = core.decide_release(
        original["slot_write"], original["receipt_write"], request,
        terminal_status="complete", verified_terminal=True, released_at=2000,
    )
    assert outcome["outcome"] == "released"
    assert outcome["slot_write"]["state"] == "released"
    same = core.decide_release(outcome["slot_write"], outcome["receipt_write"], request,
                               terminal_status="complete", verified_terminal=True, released_at=3000)
    assert same == {"outcome": "already_released"}
    with pytest.raises(core.AdmissionRefused, match="terminal_conflict"):
        core.decide_release(outcome["slot_write"], outcome["receipt_write"], request,
                            terminal_status="failed", verified_terminal=True, released_at=3000)
    prior = reserve(grant(), outcome["slot_write"], outcome["receipt_write"])
    assert prior["outcome"] == "terminal_replay"
    next_grant = grant(request="request-next")
    next_reservation = reserve(next_grant, outcome["slot_write"])
    assert next_reservation["outcome"] == "reserved"
    assert next_reservation["task_name"] != original["task_name"]
    with pytest.raises(core.AdmissionRefused, match="owner_slot_mismatch"):
        core.decide_release(next_reservation["slot_write"], outcome["receipt_write"], request,
                            terminal_status="complete", verified_terminal=True, released_at=4000)


@pytest.mark.parametrize("field,value,expected", [
    ("plan_id", "standard150_lifetime", "wrong_entitlement_plan"),
    ("entitlement_state", "preview", "paid_entitlement_required"),
    ("scan_mode", "advanced", "invalid_scan_mode"),
    ("attempt_count", True, "invalid_attempt_count"),
    ("attempt_count", 0, "invalid_attempt_count"),
    ("owner_user_id", "with/slash", "invalid_owner_user_id"),
])
def test_unpaid_or_cross_plan_or_untrusted_identity_fails(field, value, expected):
    value_to_use = {**grant(), field: value}
    with pytest.raises(core.AdmissionRefused, match=expected):
        reserve(value_to_use)


def test_task_names_are_deterministic_sanitized_and_queue_is_strict():
    first = reserve(grant())
    assert first["task_name"].startswith(QUEUE + "/tasks/extended500-")
    assert first["task_name"].endswith("-a1")
    with pytest.raises(core.AdmissionRefused, match="invalid_extended500_queue_path"):
        core.task_name("projects/foo/locations/XX/queues/x;malicious", core.canonical_request(grant()))
