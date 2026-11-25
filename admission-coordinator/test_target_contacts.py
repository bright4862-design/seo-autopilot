"""Exercise contact grants and terminal fences through the signed HTTP API."""

from unittest.mock import patch

from test_coordinator import CoordinatorTestCase, STORE, main


class TargetContactsTest(CoordinatorTestCase):
    ORIGIN = "https://site.example:443"
    REDIRECT = "https://www.site.example:443"

    def setUp(self):
        super().setUp()
        self.now = 1_800_000_000
        clock = patch.object(main.time, "time", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def claim_for(self, owner, origin=ORIGIN, request_id="request_one"):
        return self.post("/claim", {
            "owner_user_id": owner, "request_id": request_id,
            "request_fingerprint": f"standard_150|{origin}/", "target_origin": origin,
        })

    def bound_contact(self, owner, *, origin=ORIGIN, request_id="request_one"):
        claimed = self.claim_for(owner, origin, request_id)
        self.assertEqual(claimed.status_code, 200)
        scan = f"scan_{owner}_{request_id}"
        bound = self.post("/bind", {
            "owner_user_id": owner, "request_id": request_id,
            "claim_token": claimed.json["claim_token"], "scan_id": scan,
        })
        self.assertEqual(bound.status_code, 200)
        return {
            "owner_user_id": owner, "scan_id": scan, "request_id": request_id,
            "barrier_generation": claimed.json["barrier_generation"],
            "claim_sequence": claimed.json["claim_sequence"],
            "scan_target_origin": origin, "target_origin": origin,
            "attempt_count": 1, "delivery_id": "a" * 32,
        }

    def acquire(self, identity, *, deadline):
        return self.post("/acquire-target-contact", {
            **identity, "action": "acquire_target_contact_v1", "delivery_cutoff": deadline,
        })

    def settle(self, identity, *, drained_at=None, observed_at=None, delay=1200):
        observation = None if observed_at is None else {
            "status_code": 429, "observed_at": observed_at, "retry_after_seconds": delay,
            "expires_source": "retry_after",
        }
        return self.post("/settle-target-contact", {
            **identity, "action": "settle_target_contact_v1",
            "receipt": {"drained_at": self.now if drained_at is None else drained_at, "observation": observation},
        })

    def release(self, identity, terminal_status="cancelled"):
        return self.post("/release", {
            "owner_user_id": identity["owner_user_id"], "scan_id": identity["scan_id"],
            "terminal_status": terminal_status,
        })

    def test_grant_is_exclusive_and_its_cutoff_cannot_be_extended(self):
        first = self.bound_contact("first")
        second = self.bound_contact("second")
        deadline = self.now + 120
        self.assertEqual(self.acquire(first, deadline=deadline).json["seconds_remaining"], 120)
        self.now += 30
        self.assertEqual(self.acquire(first, deadline=deadline).json["seconds_remaining"], 90)
        self.assertEqual(self.acquire(first, deadline=deadline + 10).status_code, 409)
        denied = self.acquire(second, deadline=deadline)
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(denied.json["error"], "target_contact_busy")
        self.assertEqual(self.claim_for("third").json["error"], "target_contact_busy")
        queued = self.post("/claim", {
            "owner_user_id": "third", "request_id": "queued_request",
            "request_fingerprint": "standard_500|https://site.example/", "target_origin": self.ORIGIN,
            "queue_if_origin_busy": True,
        })
        self.assertEqual(queued.status_code, 200)
        self.assertEqual(self.settle(first).json["outcome"], "settled")
        self.assertEqual(self.acquire(second, deadline=deadline).status_code, 200)
        self.assertEqual(self.acquire(first, deadline=deadline).json["error"], "target_contact_closed")

    def test_cancellation_fences_new_contacts_until_all_open_origins_are_settled(self):
        first = self.bound_contact("first")
        redirect = {**first, "target_origin": self.REDIRECT}
        deadline = self.now + 120
        self.assertEqual(self.acquire(first, deadline=deadline).status_code, 200)
        self.assertEqual(self.acquire(redirect, deadline=deadline).status_code, 200)
        self.now += 1
        release = self.release(first)
        self.assertEqual(release.status_code, 503)
        self.assertEqual(release.json["error"], "target_contacts_draining")
        another_delivery = {**first, "delivery_id": "b" * 32}
        self.assertEqual(self.acquire(another_delivery, deadline=deadline).json["error"], "target_contact_closed")
        self.assertEqual(self.acquire(first, deadline=deadline).json["error"], "target_contact_closed")
        self.assertEqual(self.settle(first).json["outcome"], "settled")
        self.assertEqual(self.release(first).json["error"], "target_contacts_draining")
        self.assertEqual(self.settle(redirect).json["outcome"], "settled")
        self.assertEqual(self.release(first).json["outcome"], "released")

    def test_lost_receipt_protects_origin_across_owner_release(self):
        first = self.bound_contact("first")
        deadline = self.now + 120
        self.assertEqual(self.acquire(first, deadline=deadline).status_code, 200)
        self.now = deadline + 8
        self.assertEqual(self.release(first, "failed").json["outcome"], "released")
        denied = self.claim_for("second")
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(denied.json["error"], "target_contact_unconfirmed")
        queued = self.post("/claim", {
            "owner_user_id": "second", "request_id": "queued_request",
            "request_fingerprint": "standard_500|https://site.example/", "target_origin": self.ORIGIN,
            "queue_if_origin_busy": True,
        })
        self.assertEqual(queued.json["error"], "target_contact_unconfirmed")
        self.now = deadline + 50
        self.assertEqual(self.settle(first, drained_at=deadline - 1).json["outcome"], "protection_retained")
        self.assertEqual(self.claim_for("second").json["error"], "target_contact_unconfirmed")
        self.now = deadline + 86_400 + 8
        self.assertEqual(self.claim_for("second").status_code, 200)

    def test_redirect_receipt_commits_original_expiry_and_has_an_exact_replay(self):
        first = self.bound_contact("first")
        redirect = {**first, "target_origin": self.REDIRECT}
        self.assertEqual(self.acquire(redirect, deadline=self.now + 120).status_code, 200)
        observed = self.now + 1
        self.now += 10
        saved = self.settle(redirect, observed_at=observed)
        self.assertEqual(saved.json["outcome"], "settled")
        self.assertEqual(self.settle(redirect, observed_at=observed).json, saved.json)
        refused = self.claim_for("second", self.REDIRECT)
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.json["retry_after_seconds"], observed + 1200 - self.now)
        self.assertEqual(self.claim_for("second").status_code, 200)
        mismatched = {**redirect, "claim_sequence": redirect["claim_sequence"] + 1}
        self.assertEqual(self.settle(mismatched, observed_at=observed).status_code, 409)
        self.assertEqual(self.release(first, "limited").json["outcome"], "released")

    def test_late_receipt_keeps_new_claim_intact(self):
        first = self.bound_contact("first")
        deadline = self.now + 120
        self.assertEqual(self.acquire(first, deadline=deadline).status_code, 200)
        self.now = deadline + 30
        self.assertEqual(self.release(first, "failed").json["outcome"], "released")
        self.bound_contact("first", origin=self.REDIRECT, request_id="request_two")
        before = dict(STORE["scan_admission/first"])
        late = self.settle(first, drained_at=deadline + 1, observed_at=deadline, delay=86400)
        self.assertEqual(late.json["outcome"], "protection_retained")
        self.assertEqual(STORE["scan_admission/first"], before)
        self.assertEqual(self.claim_for("second").status_code, 429)

    def test_claim_mismatch_and_wrong_signature_never_create_a_grant(self):
        first = self.bound_contact("first")
        wrong_base_origin = {**first, "scan_target_origin": self.REDIRECT}
        self.assertEqual(self.acquire(wrong_base_origin, deadline=self.now + 120).status_code, 409)
        wrong_scope = {**first, "claim_sequence": first["claim_sequence"] + 1}
        self.assertEqual(self.acquire(wrong_scope, deadline=self.now + 120).status_code, 409)
        refused = self.post("/acquire-target-contact", {
            **first, "action": "acquire_target_contact_v1", "delivery_cutoff": self.now + 120,
        }, signature="a" * 64)
        self.assertEqual(refused.status_code, 401)
        self.assertEqual(self.claim_for("second").status_code, 200)
