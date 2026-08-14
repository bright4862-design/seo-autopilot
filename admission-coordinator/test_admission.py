"""State-machine coverage for the admission coordinator.

These tests import only ``admission``, which has no third-party dependencies,
so the full admission contract is provable with a stock Python interpreter and
no Firestore emulator. Each test names the release scenario it discharges.
"""

import unittest

import admission

NOW = 1_760_000_000
LEASE = 900
OWNER = "6a498da58ef5cec1f5cd4486"
FINGERPRINT = "standard_150|https://funbooker.com/"


def claim(document, *, request_id="req_alpha", fingerprint=FINGERPRINT, token="tok_alpha", now=NOW):
    return admission.decide_claim(
        document,
        owner_user_id=OWNER,
        request_id=request_id,
        request_fingerprint=fingerprint,
        claim_token=token,
        now=now,
        lease_seconds=LEASE,
    )


def win(**kwargs):
    """A freshly claimed document, as persisted by a winning transaction."""
    return claim(None, **kwargs)["write"]


def bound(scan_id="6a7f606b1f3c36298704c439", **kwargs):
    document = win(**kwargs)
    decision = admission.decide_bind(
        document,
        request_id=document["request_id"],
        claim_token=document["claim_token"],
        scan_id=scan_id,
        now=NOW,
    )
    return decision["write"]


class ClaimAdmission(unittest.TestCase):
    def test_first_caller_wins_on_empty_document(self):
        decision = claim(None)
        self.assertEqual(decision["outcome"], admission.OUTCOME_CLAIMED)
        written = decision["write"]
        self.assertEqual(written["state"], admission.STATE_CLAIMED)
        self.assertEqual(written["request_id"], "req_alpha")
        self.assertEqual(written["lease_expires_at"], NOW + LEASE)
        # No ScanRun exists yet. Admission is won before anything is created,
        # which is what makes the create recoverable if its response is lost.
        self.assertEqual(written["scan_id"], "")

    def test_two_tabs_same_request_replay_one_claim(self):
        """Scenario 5 -- two tabs, same request, one canonical ScanRun."""
        first = win()
        second = claim(first, request_id="req_alpha", fingerprint=FINGERPRINT, token="tok_second")
        self.assertEqual(second["outcome"], admission.OUTCOME_REPLAYED)
        self.assertNotIn("write", second)
        # The second caller is handed the original token, not its own, so both
        # tabs drive the same claim rather than racing two.
        self.assertEqual(second["claim_token"], "tok_alpha")

    def test_replay_returns_bound_scan_id(self):
        """Scenario 5 -- the late tab is told which ScanRun already won."""
        document = bound()
        replay = claim(document, request_id=document["request_id"], token="tok_late")
        self.assertEqual(replay["outcome"], admission.OUTCOME_REPLAYED)
        self.assertEqual(replay["scan_id"], "6a7f606b1f3c36298704c439")

    def test_two_tabs_different_request_one_winner_one_busy(self):
        """Scenario 6 -- one winner, one busy, nothing created for the loser."""
        first = win(request_id="req_alpha")
        second = claim(first, request_id="req_beta", token="tok_beta")
        self.assertEqual(second["outcome"], admission.OUTCOME_BUSY)
        self.assertNotIn("write", second)
        self.assertGreater(second["retry_after_seconds"], 0)

    def test_same_request_different_fingerprint_fails_closed(self):
        """Scenario 8 -- a reused request id with different work is refused."""
        first = win()
        second = claim(first, request_id="req_alpha", fingerprint="standard_150|https://evil.example/")
        self.assertEqual(second["error"], admission.ERROR_REQUEST_CONFLICT)
        self.assertNotIn("write", second)

    def test_expired_lease_can_be_reclaimed(self):
        """Scenario 10 -- a vanished worker's lease does not wedge the owner."""
        first = win()
        later = first["lease_expires_at"] + 1
        second = claim(first, request_id="req_beta", token="tok_beta", now=later)
        self.assertEqual(second["outcome"], admission.OUTCOME_CLAIMED)
        self.assertEqual(second["write"]["request_id"], "req_beta")

    def test_lease_is_still_held_one_second_before_expiry(self):
        first = win()
        edge = first["lease_expires_at"] - 1
        second = claim(first, request_id="req_beta", token="tok_beta", now=edge)
        self.assertEqual(second["outcome"], admission.OUTCOME_BUSY)

    def test_released_document_admits_immediately(self):
        """Scenario 9 -- a terminal scan frees the next admission at once."""
        document = bound()
        released = admission.decide_release(
            document, scan_id=document["scan_id"], terminal_status="complete", now=NOW + 10
        )["write"]
        nxt = claim(released, request_id="req_beta", token="tok_beta", now=NOW + 11)
        self.assertEqual(nxt["outcome"], admission.OUTCOME_CLAIMED)

    def test_malformed_identity_is_rejected(self):
        for bad in ["", "   ", "has space", "semi;colon", "x" * 129]:
            with self.assertRaises(admission.AdmissionError):
                claim(None, request_id=bad)

    def test_lease_bounds_are_clamped_to_the_default(self):
        self.assertEqual(admission.normalize_lease_seconds(10), admission.DEFAULT_LEASE_SECONDS)
        self.assertEqual(admission.normalize_lease_seconds(99999), admission.DEFAULT_LEASE_SECONDS)
        self.assertEqual(admission.normalize_lease_seconds("nonsense"), admission.DEFAULT_LEASE_SECONDS)
        self.assertEqual(admission.normalize_lease_seconds(600), 600)


class BindCanonicalScanRun(unittest.TestCase):
    def test_bind_writes_the_canonical_id(self):
        document = win()
        decision = admission.decide_bind(
            document,
            request_id="req_alpha",
            claim_token="tok_alpha",
            scan_id="6a7f606b1f3c36298704c439",
            now=NOW,
        )
        self.assertEqual(decision["outcome"], admission.OUTCOME_BOUND)
        self.assertEqual(decision["write"]["scan_id"], "6a7f606b1f3c36298704c439")
        self.assertEqual(decision["write"]["state"], admission.STATE_BOUND)

    def test_rebinding_the_same_id_is_idempotent(self):
        """Scenario 7 -- the create succeeded but its response was lost."""
        document = bound()
        decision = admission.decide_bind(
            document,
            request_id=document["request_id"],
            claim_token=document["claim_token"],
            scan_id="6a7f606b1f3c36298704c439",
            now=NOW,
        )
        self.assertEqual(decision["outcome"], admission.OUTCOME_ALREADY_BOUND)
        self.assertNotIn("write", decision)

    def test_binding_a_second_id_fails_closed(self):
        """The defect this whole design exists to prevent: two rows, one request."""
        document = bound()
        decision = admission.decide_bind(
            document,
            request_id=document["request_id"],
            claim_token=document["claim_token"],
            scan_id="6a7f518b619f437d8c363983",
            now=NOW,
        )
        self.assertEqual(decision["error"], admission.ERROR_SCAN_IDENTITY_CONFLICT)
        self.assertNotIn("write", decision)

    def test_wrong_token_cannot_bind(self):
        document = win()
        decision = admission.decide_bind(
            document, request_id="req_alpha", claim_token="tok_forged", scan_id="scan_x", now=NOW
        )
        self.assertEqual(decision["error"], admission.ERROR_INVALID_CLAIM_TOKEN)

    def test_wrong_request_cannot_bind(self):
        document = win()
        decision = admission.decide_bind(
            document, request_id="req_beta", claim_token="tok_alpha", scan_id="scan_x", now=NOW
        )
        self.assertEqual(decision["error"], admission.ERROR_REQUEST_CONFLICT)

    def test_expired_claim_cannot_bind(self):
        document = win()
        decision = admission.decide_bind(
            document,
            request_id="req_alpha",
            claim_token="tok_alpha",
            scan_id="scan_x",
            now=document["lease_expires_at"] + 1,
        )
        self.assertEqual(decision["error"], admission.ERROR_CLAIM_EXPIRED)

    def test_bind_without_a_claim_fails_closed(self):
        decision = admission.decide_bind(
            None, request_id="req_alpha", claim_token="tok_alpha", scan_id="scan_x", now=NOW
        )
        self.assertEqual(decision["error"], admission.ERROR_CLAIM_NOT_FOUND)


class TerminalRelease(unittest.TestCase):
    def test_worker_success_releases(self):
        """Scenario 2 -- worker succeeds, terminal result persists."""
        document = bound()
        decision = admission.decide_release(
            document, scan_id=document["scan_id"], terminal_status="complete", now=NOW + 60
        )
        self.assertEqual(decision["outcome"], admission.OUTCOME_RELEASED)
        self.assertEqual(decision["write"]["terminal_status"], "complete")
        self.assertEqual(decision["write"]["released_at"], NOW + 60)

    def test_worker_failure_releases(self):
        """Scenario 3 -- worker fails, terminal failure persists."""
        document = bound()
        decision = admission.decide_release(
            document, scan_id=document["scan_id"], terminal_status="failed", now=NOW + 60
        )
        self.assertEqual(decision["outcome"], admission.OUTCOME_RELEASED)
        self.assertEqual(decision["write"]["terminal_status"], "failed")

    def test_every_terminal_status_releases(self):
        for status in ["complete", "limited", "failed", "cancelled"]:
            document = bound()
            decision = admission.decide_release(
                document, scan_id=document["scan_id"], terminal_status=status, now=NOW + 5
            )
            self.assertEqual(decision["outcome"], admission.OUTCOME_RELEASED, status)

    def test_non_terminal_status_cannot_release(self):
        """A crawling scan may not free its own admission."""
        document = bound()
        for status in ["crawling", "queued", "reviewing", "", "COMPLETE-ish"]:
            decision = admission.decide_release(
                document, scan_id=document["scan_id"], terminal_status=status, now=NOW
            )
            self.assertEqual(decision["error"], admission.ERROR_NOT_TERMINAL, status)

    def test_release_requires_the_bound_scan_id(self):
        """A stale run cannot release the admission a newer scan now holds."""
        document = bound(scan_id="6a7f606b1f3c36298704c439")
        decision = admission.decide_release(
            document, scan_id="6a7f518b619f437d8c363983", terminal_status="failed", now=NOW
        )
        self.assertEqual(decision["error"], admission.ERROR_SCAN_IDENTITY_CONFLICT)
        self.assertNotIn("write", decision)

    def test_release_before_bind_fails_closed(self):
        document = win()
        decision = admission.decide_release(
            document, scan_id="scan_x", terminal_status="complete", now=NOW
        )
        self.assertEqual(decision["error"], admission.ERROR_SCAN_NOT_BOUND)

    def test_double_release_is_idempotent(self):
        """The worker and the watchdog may both report the same terminal state."""
        document = bound()
        first = admission.decide_release(
            document, scan_id=document["scan_id"], terminal_status="complete", now=NOW + 10
        )["write"]
        second = admission.decide_release(
            first, scan_id=first["scan_id"], terminal_status="complete", now=NOW + 20
        )
        self.assertEqual(second["outcome"], admission.OUTCOME_ALREADY_RELEASED)
        self.assertNotIn("write", second)
        # The first release remains the record of what happened.
        self.assertEqual(first["released_at"], NOW + 10)

    def test_watchdog_can_terminalize_a_vanished_worker(self):
        """Scenario 4 -- nothing but the server closes an abandoned run."""
        document = bound()
        decision = admission.decide_release(
            document,
            scan_id=document["scan_id"],
            terminal_status="failed",
            now=document["lease_expires_at"] + 1,
        )
        # Release deliberately does not require a live lease: the whole point is
        # to close a run whose lease already lapsed.
        self.assertEqual(decision["outcome"], admission.OUTCOME_RELEASED)


class DocumentShape(unittest.TestCase):
    def test_document_carries_only_coordination_metadata(self):
        """No scan evidence, authority proof, payment state or customer content."""
        self.assertEqual(
            set(bound().keys()),
            {
                "owner_user_id",
                "request_id",
                "request_fingerprint",
                "claim_token",
                "scan_id",
                "state",
                "claimed_at",
                "lease_expires_at",
                "released_at",
                "terminal_status",
            },
        )

    def test_public_view_never_leaks_the_claim_token(self):
        view = admission.public_view(bound())
        self.assertNotIn("claim_token", view)
        self.assertNotIn("request_fingerprint", view)

    def test_public_view_tolerates_a_missing_document(self):
        self.assertEqual(admission.public_view(None)["state"], "")


if __name__ == "__main__":
    unittest.main()
