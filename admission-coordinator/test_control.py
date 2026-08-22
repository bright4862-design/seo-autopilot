"""Pure Patch E barrier, cohort, drain, and reconciliation contracts."""

from __future__ import annotations

import json
import unittest

import admission
import control


NOW = 1_760_000_000
OWNER = "owner_alpha"
OTHER = "owner_beta"
SHA = "a" * 40
ROOT = "operator-root-for-tests"
CONTEXT = {
    "operator_id": "release_operator",
    "reason": "Patch E acceptance cutover",
    "change_ticket": "release/patch-e-123",
}


def open_control(**updates):
    return {
        "mode": admission.BARRIER_OPEN,
        "generation": 3,
        "claim_sequence": 8,
        "reconciliation_sequence": 2,
        **updates,
    }


def acceptance_definition(**updates):
    return {
        "version": control.ACCEPTANCE_COHORT_VERSION,
        "cohort_id": "cohort_patch_e",
        "release_id": "release_patch_e",
        "source_sha": SHA,
        "owner_allowlist": [OWNER],
        "expires_at": NOW + 600,
        "total_claim_budget": 2,
        "per_owner_claim_budget": 2,
        "created_at": NOW,
        "created_by": "release_operator",
        **updates,
    }


def admission_document(
    *,
    owner=OWNER,
    request="request_alpha",
    scan="",
    state=admission.STATE_CLAIMED,
    expires=NOW + 60,
    sequence=9,
):
    return admission.decide_claim(
        None,
        owner_user_id=owner,
        request_id=request,
        request_fingerprint="standard_150|https://example.com/",
        claim_token="capability_token",
        now=NOW,
        lease_seconds=900,
        barrier_generation=4,
        claim_sequence=sequence,
    )["write"] | {
        "scan_id": scan,
        "state": state,
        "lease_expires_at": expires,
    }


class BarrierPolicyTests(unittest.TestCase):
    def test_missing_control_is_generation_zero_open(self):
        current = admission.normalized_control(None)
        self.assertEqual(current["mode"], admission.BARRIER_OPEN)
        self.assertEqual(current["generation"], 0)
        self.assertEqual(current["claim_sequence"], 0)
        self.assertEqual(current["reconciliation_sequence"], 0)

    def test_closed_barrier_uses_one_public_error(self):
        policy = admission.decide_claim_policy(
            open_control(mode=admission.BARRIER_CLOSED), owner_user_id=OWNER, now=NOW
        )
        self.assertFalse(policy["allowed"])
        self.assertEqual(policy["error"], admission.ERROR_SCAN_INTAKE_PAUSED)

    def test_acceptance_membership_and_expiry_are_server_owned(self):
        barrier = open_control(
            mode=admission.BARRIER_ACCEPTANCE_ONLY,
            acceptance={**acceptance_definition(), "total_claims_used": 0, "owner_claims_used": {}},
        )
        self.assertTrue(
            admission.decide_claim_policy(barrier, owner_user_id=OWNER, now=NOW)["allowed"]
        )
        for owner, moment in [(OTHER, NOW), (OWNER, NOW + 601)]:
            decision = admission.decide_claim_policy(barrier, owner_user_id=owner, now=moment)
            self.assertFalse(decision["allowed"])
            self.assertEqual(decision["error"], admission.ERROR_SCAN_INTAKE_PAUSED)

    def test_fresh_acceptance_reservation_is_monotonic_and_budgeted(self):
        barrier = open_control(
            mode=admission.BARRIER_ACCEPTANCE_ONLY,
            acceptance={**acceptance_definition(), "total_claims_used": 0, "owner_claims_used": {}},
        )
        first = admission.reserve_fresh_claim(barrier, owner_user_id=OWNER, now=NOW)
        self.assertEqual(first["claim_sequence"], 9)
        self.assertEqual(first["control_write"]["acceptance"]["total_claims_used"], 1)
        second = admission.reserve_fresh_claim(
            first["control_write"], owner_user_id=OWNER, now=NOW
        )
        self.assertEqual(second["claim_sequence"], 10)
        exhausted = admission.reserve_fresh_claim(
            second["control_write"], owner_user_id=OWNER, now=NOW
        )
        self.assertFalse(exhausted["allowed"])
        self.assertEqual(exhausted["error"], admission.ERROR_SCAN_INTAKE_PAUSED)

    def test_bind_is_generation_bound_and_echoes_exact_identity(self):
        document = admission_document()
        wrong = admission.decide_bind(
            document,
            request_id="request_alpha",
            claim_token="capability_token",
            scan_id="scan_alpha",
            now=NOW,
            barrier_generation=3,
        )
        self.assertEqual(wrong["error"], admission.ERROR_BARRIER_GENERATION_CONFLICT)
        bound = admission.decide_bind(
            document,
            request_id="request_alpha",
            claim_token="capability_token",
            scan_id="scan_alpha",
            now=NOW,
            barrier_generation=4,
        )
        self.assertEqual(
            {key: bound[key] for key in ("request_id", "scan_id", "barrier_generation", "claim_sequence")},
            {
                "request_id": "request_alpha",
                "scan_id": "scan_alpha",
                "barrier_generation": 4,
                "claim_sequence": 9,
            },
        )

    def test_release_and_satisfy_unbound_echo_supersession_markers(self):
        claimed = admission_document(expires=NOW - 1)
        satisfied = admission.decide_satisfy_unbound(
            claimed,
            request_id="request_alpha",
            barrier_generation=4,
            now=NOW,
        )
        self.assertEqual(satisfied["scan_id"], "")
        self.assertEqual(satisfied["claim_sequence"], 9)
        active = admission.decide_satisfy_unbound(
            admission_document(),
            request_id="request_alpha",
            barrier_generation=4,
            now=NOW,
        )
        self.assertEqual(active["error"], admission.ERROR_CLAIM_STILL_ACTIVE)
        bound_doc = admission_document(scan="scan_alpha", state=admission.STATE_BOUND)
        released = admission.decide_release(
            bound_doc, scan_id="scan_alpha", terminal_status="complete", now=NOW
        )
        self.assertEqual(released["request_id"], "request_alpha")
        self.assertEqual(released["barrier_generation"], 4)
        self.assertEqual(released["claim_sequence"], 9)


class ControlTransitionTests(unittest.TestCase):
    def test_close_open_and_acceptance_each_advance_generation(self):
        closed = control.close_control(
            open_control(), snapshot_id="snapshot_close", now=NOW, **CONTEXT
        )
        self.assertEqual((closed["mode"], closed["generation"]), ("closed", 4))
        opened = control.open_control(
            closed, snapshot_id="snapshot_open", now=NOW + 1, **CONTEXT
        )
        self.assertEqual((opened["mode"], opened["generation"]), ("open", 5))
        closed_again = control.close_control(
            opened, snapshot_id="snapshot_close_2", now=NOW + 2, **CONTEXT
        )
        acceptance = control.acceptance_control(
            closed_again,
            acceptance_definition(),
            snapshot_id="snapshot_acceptance",
            now=NOW + 3,
            **CONTEXT,
        )
        self.assertEqual(acceptance["mode"], admission.BARRIER_ACCEPTANCE_ONLY)
        self.assertEqual(acceptance["generation"], 7)
        self.assertEqual(acceptance["acceptance"]["total_claims_used"], 0)

    def test_only_an_exact_committed_close_is_replayable(self):
        closed = control.close_control(
            open_control(), snapshot_id="snapshot_close", now=NOW, **CONTEXT
        )
        closed["close_audit_event_id"] = "audit_close"
        intended = {"mode": "open", "generation": 3}
        self.assertTrue(control.is_exact_close_replay(closed, intended, **CONTEXT))
        self.assertFalse(control.is_exact_close_replay(
            closed,
            intended,
            operator_id=CONTEXT["operator_id"],
            reason="a different reason",
            change_ticket=CONTEXT["change_ticket"],
        ))

    def test_acceptance_definition_is_bounded_and_signed(self):
        definition = control.acceptance_definition(
            {
                "cohort_id": "cohort_patch_e",
                "release_id": "release_patch_e",
                "source_sha": SHA,
                "owner_user_ids": [OWNER, OTHER],
                "expires_at": NOW + 600,
                "total_claim_budget": 3,
                "per_owner_claim_budget": 2,
            },
            now=NOW,
            operator_id="release_operator",
        )
        signed = control.signed_acceptance_definition(definition, ROOT)
        proof = signed.pop("proof")
        self.assertTrue(control.verify_record(ROOT, control.COHORT_LABEL, signed, proof))
        with self.assertRaisesRegex(control.ControlError, "invalid_acceptance_owner_allowlist"):
            control.acceptance_definition(
                {
                    "cohort_id": "cohort_patch_e",
                    "release_id": "release_patch_e",
                    "source_sha": SHA,
                    "owner_user_ids": [OWNER, OWNER],
                    "expires_at": NOW + 600,
                    "total_claim_budget": 3,
                    "per_owner_claim_budget": 2,
                },
                now=NOW,
                operator_id="release_operator",
            )


class DrainSnapshotTests(unittest.TestCase):
    def snapshot(self, admissions=None, reconciliations=None):
        return control.build_snapshot(
            snapshot_id="snapshot_patch_e",
            control=open_control(mode=admission.BARRIER_CLOSED),
            admission_documents=list(admissions or []),
            reconciliation_documents=list(reconciliations or []),
            now=NOW,
            signing_root=ROOT,
            boundary={"claim_sequence_cutoff": 8},
            **CONTEXT,
        )

    def test_expired_unbound_is_diagnostic_but_not_a_drain_blocker(self):
        snapshot = self.snapshot([admission_document(expires=NOW - 1)])
        self.assertTrue(snapshot["drain_ready"])
        self.assertEqual(snapshot["counts"]["claimed_expired"], 1)
        self.assertEqual(snapshot["counts"]["total_obligations"], 1)

    def test_only_semantic_live_obligations_block_drain(self):
        live_reconciler = {
            "state": "live",
            "invocation_id": "reconcile_alpha",
            "source_sha": SHA,
            "started_at": NOW - 10,
            "lease_expires_at": NOW + 10,
            "barrier_generation": 3,
            "reconciliation_sequence": 1,
        }
        cases = [
            ([admission_document()], [], "claimed_active"),
            ([admission_document(scan="scan_alpha", state=admission.STATE_BOUND)], [], "bound"),
            ([], [live_reconciler], "live_reconciliation"),
        ]
        for admissions, invocations, counter in cases:
            snapshot = self.snapshot(admissions, invocations)
            self.assertFalse(snapshot["drain_ready"], counter)
            self.assertEqual(snapshot["counts"][counter], 1)

    def test_snapshot_is_signed_bounded_and_secret_free(self):
        admissions = [
            admission_document(
                owner=f"owner_{index}",
                request=f"request_{index}",
                sequence=index + 1,
            )
            | {"request_fingerprint": f"secret-fingerprint-{index}", "claim_token": f"secret-{index}"}
            for index in range(70)
        ]
        snapshot = self.snapshot(admissions)
        public = control.public_snapshot(snapshot)
        self.assertEqual(len(public["admission_obligation_sample"]), 64)
        self.assertEqual(public["counts"]["total_obligations"], 70)
        self.assertRegex(public["admission_obligations_digest"], r"^[a-f0-9]{64}$")
        self.assertNotIn("_internal_admission_obligations", public)
        serialized = json.dumps(public)
        self.assertNotIn("claim_token", serialized)
        self.assertNotIn("request_fingerprint", serialized)
        self.assertNotIn("secret-fingerprint", serialized)
        unsigned = {key: value for key, value in public.items() if key != "proof"}
        self.assertTrue(
            control.verify_record(ROOT, control.SNAPSHOT_LABEL, unsigned, public["proof"])
        )

    def test_snapshot_refuses_to_silently_truncate_internal_obligations(self):
        admissions = [
            admission_document(owner=f"owner_{index}", request=f"req_{index}", sequence=index)
            for index in range(control.MAX_INTERNAL_OBLIGATIONS + 1)
        ]
        with self.assertRaisesRegex(control.ControlError, "drain_snapshot_capacity_exceeded"):
            self.snapshot(admissions)


class ReconciliationFsmTests(unittest.TestCase):
    def test_start_is_barrier_bound_and_finish_is_idempotent(self):
        started = control.decide_reconciliation_start(
            None,
            open_control(),
            invocation_id="reconcile_alpha",
            source_sha=SHA,
            lease_seconds=60,
            now=NOW,
        )
        self.assertEqual(started["outcome"], "started")
        self.assertEqual(started["control_write"]["reconciliation_sequence"], 3)
        self.assertEqual(started["invocation"]["barrier_generation"], 3)
        replay = control.decide_reconciliation_start(
            started["write"],
            started["control_write"],
            invocation_id="reconcile_alpha",
            source_sha=SHA,
            lease_seconds=60,
            now=NOW + 1,
        )
        self.assertEqual(replay["outcome"], "already_started")
        finished = control.decide_reconciliation_finish(
            started["write"],
            invocation_id="reconcile_alpha",
            source_sha=SHA,
            outcome="success",
            now=NOW + 2,
        )
        self.assertEqual(finished["outcome"], "finished")
        duplicate = control.decide_reconciliation_finish(
            finished["write"],
            invocation_id="reconcile_alpha",
            source_sha=SHA,
            outcome="success",
            now=NOW + 3,
        )
        self.assertEqual(duplicate["outcome"], "already_finished")

    def test_closed_barrier_still_allows_fresh_reconciler_to_drain(self):
        started = control.decide_reconciliation_start(
            None,
            open_control(mode=admission.BARRIER_CLOSED),
            invocation_id="reconcile_alpha",
            source_sha=SHA,
            lease_seconds=60,
            now=NOW,
        )
        self.assertEqual(started["outcome"], "started")
        self.assertEqual(started["write"]["barrier_generation"], 3)
        self.assertEqual(started["control_write"]["mode"], admission.BARRIER_CLOSED)

    def test_expired_invocation_and_identity_conflicts_fail_closed(self):
        started = control.decide_reconciliation_start(
            None,
            open_control(),
            invocation_id="reconcile_alpha",
            source_sha=SHA,
            lease_seconds=60,
            now=NOW,
        )["write"]
        expired = control.decide_reconciliation_start(
            started,
            open_control(),
            invocation_id="reconcile_alpha",
            source_sha=SHA,
            lease_seconds=60,
            now=NOW + 61,
        )
        self.assertEqual(expired["error"], "reconciliation_invocation_expired")
        conflict = control.decide_reconciliation_finish(
            started,
            invocation_id="reconcile_alpha",
            source_sha="b" * 40,
            outcome="success",
            now=NOW + 1,
        )
        self.assertEqual(conflict["error"], "reconciliation_identity_conflict")


if __name__ == "__main__":
    unittest.main()
