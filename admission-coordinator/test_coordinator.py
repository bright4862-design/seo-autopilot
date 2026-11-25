"""HTTP-surface coverage for the admission coordinator.

Firestore is replaced with an in-process fake so the transaction wiring, the
HMAC boundary and the full claim/bind/release lifecycle are provable without a
network, an emulator or credentials. The fake is installed into ``sys.modules``
before ``main`` is imported, because ``main`` binds ``firestore`` at import time.
"""

import contextlib
from copy import deepcopy
import hashlib
import hmac
import importlib
import io
import json
import os
import sys
import time
import types
import unittest
from unittest.mock import patch

STORE: dict[str, dict] = {}


class FakeSnapshot:
    def __init__(self, data, key=""):
        self._data = data
        self.id = key.rsplit("/", 1)[-1]

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocumentRef:
    def __init__(self, key):
        self.key = key

    def get(self, transaction=None):
        return FakeSnapshot(STORE.get(self.key), self.key)


class FakeCollection:
    def __init__(self, name):
        self.name = name

    def document(self, key):
        return FakeDocumentRef(f"{self.name}/{key}")

    def where(self, field, operator, value):
        return FakeQuery(self.name, [(field, operator, value)])


class FakeQuery:
    def __init__(self, collection, filters=None, maximum=None):
        self.collection = collection
        self.filters = list(filters or [])
        self.maximum = maximum

    def where(self, field, operator, value):
        return FakeQuery(self.collection, [*self.filters, (field, operator, value)], self.maximum)

    def limit(self, maximum):
        return FakeQuery(self.collection, self.filters, int(maximum))


class FakeTransaction:
    def get(self, query):
        prefix = f"{query.collection}/"
        snapshots = []
        for key, value in sorted(STORE.items()):
            if not key.startswith(prefix):
                continue
            matches = True
            for field, operator, expected in query.filters:
                actual = value.get(field)
                if operator == "==":
                    matches = matches and actual == expected
                elif operator == "in":
                    matches = matches and actual in expected
                else:
                    raise AssertionError(f"unsupported fake query operator: {operator}")
            if matches:
                snapshots.append(FakeSnapshot(value, key))
        return snapshots[:query.maximum] if query.maximum is not None else snapshots

    def set(self, ref, value):
        STORE[ref.key] = dict(value)

    def create(self, ref, value):
        if ref.key in STORE:
            raise RuntimeError("document already exists")
        STORE[ref.key] = dict(value)


class FakeClient:
    def __init__(self, **_kwargs):
        pass

    def collection(self, name):
        return FakeCollection(name)

    def transaction(self):
        return FakeTransaction()


def _install_firestore_stub():
    google_mod = sys.modules.get("google") or types.ModuleType("google")
    sys.modules["google"] = google_mod
    cloud_mod = sys.modules.get("google.cloud") or types.ModuleType("google.cloud")
    sys.modules["google.cloud"] = cloud_mod
    google_mod.cloud = cloud_mod

    firestore_mod = types.ModuleType("google.cloud.firestore")
    firestore_mod.Client = FakeClient
    firestore_mod.Transaction = FakeTransaction
    # The real decorator wraps a function so it runs inside a retried
    # transaction. The fake runs it once, directly, which is what makes the
    # decision logic observable.
    firestore_mod.transactional = lambda fn: fn
    sys.modules["google.cloud.firestore"] = firestore_mod
    cloud_mod.firestore = firestore_mod


_install_firestore_stub()

SIGNING_ROOT = "unit-test-signing-root"
OPERATOR_SIGNING_ROOT = "unit-test-operator-signing-root"
OPERATOR_SERVICE_ACCOUNT = "fixlist-operator@example.iam.gserviceaccount.com"
OPERATOR_AUDIENCE = "https://admission.example.test"
OPERATOR_ID = "release_operator"
os.environ.setdefault("SCAN_EVIDENCE_SIGNING_KEY", SIGNING_ROOT)
os.environ.setdefault("ADMISSION_OPERATOR_SIGNING_KEY", OPERATOR_SIGNING_ROOT)
os.environ.setdefault("ADMISSION_OPERATOR_SERVICE_ACCOUNT", OPERATOR_SERVICE_ACCOUNT)
os.environ.setdefault("ADMISSION_OPERATOR_AUDIENCE", OPERATOR_AUDIENCE)
os.environ.setdefault("ADMISSION_OPERATOR_ID", OPERATOR_ID)

main = importlib.import_module("main")
import admission  # noqa: E402  (imported after the stub is installed)
import control  # noqa: E402

main.OPERATOR_TOKEN_VERIFIER = lambda _token, _audience: {
    "iss": "https://accounts.google.com",
    "aud": main.OPERATOR_AUDIENCE,
    "email": main.OPERATOR_SERVICE_ACCOUNT,
    "email_verified": True,
}

OWNER = "6a498da58ef5cec1f5cd4486"
FINGERPRINT = "standard_150|https://funbooker.com/"
SCAN_ID = "6a7f606b1f3c36298704c439"


def sign(
    body: bytes,
    timestamp: str,
    label: bytes = b"fixlist-admission-coordinator-v1",
    root: str = SIGNING_ROOT,
) -> str:
    key = hmac.new(root.encode("utf-8"), label, hashlib.sha256).digest()
    return hmac.new(key, timestamp.encode("ascii") + b"\n" + body, hashlib.sha256).hexdigest()


class CoordinatorTestCase(unittest.TestCase):
    def setUp(self):
        STORE.clear()
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def post(
        self,
        path,
        payload,
        *,
        timestamp=None,
        signature=None,
        label=None,
        raw=None,
        inject_barrier=True,
    ):
        if (
            inject_barrier
            and path == "/bind"
            and isinstance(payload, dict)
            and "barrier_generation" not in payload
        ):
            owner = str(payload.get("owner_user_id") or "")
            generation = STORE.get(f"scan_admission/{owner}", {}).get("barrier_generation", 0)
            payload = {**payload, "barrier_generation": generation}
        body = raw if raw is not None else json.dumps(payload).encode("utf-8")
        stamp = timestamp if timestamp is not None else str(int(time.time()))
        sig = signature if signature is not None else sign(body, stamp, label or b"fixlist-admission-coordinator-v1")
        return self.client.post(
            path,
            data=body,
            headers={
                "content-type": "application/json",
                "x-fixlist-timestamp": stamp,
                "x-fixlist-signature": sig,
            },
        )

    def operator_post(self, path, payload, *, root=OPERATOR_SIGNING_ROOT, token="valid-oidc"):
        body = json.dumps(payload).encode("utf-8")
        stamp = str(int(time.time()))
        signature = sign(
            body,
            stamp,
            b"fixlist-admission-operator-v1",
            root=root,
        )
        return self.client.post(
            path,
            data=body,
            headers={
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "x-fixlist-operator-timestamp": stamp,
                "x-fixlist-operator-signature": signature,
            },
        )

    def claim(self, request_id="req_alpha", fingerprint=FINGERPRINT, owner=OWNER):
        return self.post("/claim", {
            "owner_user_id": owner,
            "request_id": request_id,
            "request_fingerprint": fingerprint,
        })


class Authentication(CoordinatorTestCase):
    def test_health_needs_no_signature(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["service"], "fixlist-admission-coordinator")
        self.assertEqual(response.json["source_sha"], "")

    def test_valid_signature_is_accepted(self):
        self.assertEqual(self.claim().status_code, 200)

    def test_forged_signature_is_rejected(self):
        response = self.post("/claim", {"owner_user_id": OWNER}, signature="00" * 32)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "invalid_signature")

    def test_missing_signature_is_rejected(self):
        response = self.client.post(
            "/claim",
            data=b"{}",
            headers={"content-type": "application/json", "x-fixlist-timestamp": str(int(time.time()))},
        )
        self.assertEqual(response.status_code, 401)

    def test_stale_timestamp_is_rejected(self):
        stale = str(int(time.time()) - 400)
        response = self.post("/claim", {"owner_user_id": OWNER}, timestamp=stale)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "stale_request")

    def test_future_timestamp_is_rejected(self):
        ahead = str(int(time.time()) + 400)
        response = self.post("/claim", {"owner_user_id": OWNER}, timestamp=ahead)
        self.assertEqual(response.status_code, 401)

    def test_non_numeric_timestamp_is_rejected(self):
        response = self.post("/claim", {"owner_user_id": OWNER}, timestamp="not-a-time")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "invalid_timestamp")

    def test_dispatch_gateway_signature_does_not_authenticate_here(self):
        """Domain separation: the two services share a root but not a key."""
        response = self.post(
            "/claim",
            {"owner_user_id": OWNER, "request_id": "req_alpha", "request_fingerprint": FINGERPRINT},
            label=b"fixlist-dispatch-gateway-v1",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "invalid_signature")

    def test_signature_covers_the_body(self):
        stamp = str(int(time.time()))
        honest = json.dumps({"owner_user_id": OWNER, "request_id": "req_alpha",
                             "request_fingerprint": FINGERPRINT}).encode("utf-8")
        tampered = json.dumps({"owner_user_id": "someone-else", "request_id": "req_alpha",
                               "request_fingerprint": FINGERPRINT}).encode("utf-8")
        response = self.post("/claim", None, raw=tampered, timestamp=stamp, signature=sign(honest, stamp))
        self.assertEqual(response.status_code, 401)

    def test_oversized_body_is_refused(self):
        response = self.post("/claim", None, raw=b"x" * (main.MAX_BODY_BYTES + 1))
        self.assertEqual(response.status_code, 413)

    def test_malformed_json_is_refused(self):
        response = self.post("/claim", None, raw=b"{not json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_json")


class Lifecycle(CoordinatorTestCase):
    def test_claim_bind_release_round_trip(self):
        claimed = self.claim()
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json["outcome"], admission.OUTCOME_CLAIMED)
        token = claimed.json["claim_token"]
        self.assertTrue(token)
        self.assertEqual(claimed.json["scan_id"], "")

        bound = self.post("/bind", {
            "owner_user_id": OWNER, "request_id": "req_alpha",
            "claim_token": token, "scan_id": SCAN_ID,
        })
        self.assertEqual(bound.status_code, 200)
        self.assertEqual(bound.json["outcome"], admission.OUTCOME_BOUND)

        released = self.post("/release", {
            "owner_user_id": OWNER, "scan_id": SCAN_ID, "terminal_status": "complete",
        })
        self.assertEqual(released.status_code, 200)
        self.assertEqual(released.json["outcome"], admission.OUTCOME_RELEASED)

        # Scenario 9 -- the next scan is admitted immediately.
        self.assertEqual(self.claim(request_id="req_beta").json["outcome"], admission.OUTCOME_CLAIMED)

    def test_two_tabs_different_request_second_is_busy(self):
        """Scenario 6, through the real HTTP surface and one shared document."""
        self.assertEqual(self.claim(request_id="req_alpha").status_code, 200)
        second = self.claim(request_id="req_beta")
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json["error"], "admission_busy")
        # Nothing was written on the losing path.
        self.assertEqual(STORE[f"scan_admission/{OWNER}"]["request_id"], "req_alpha")

    def test_two_tabs_same_request_share_one_claim(self):
        """Scenario 5 -- both tabs drive the same admission."""
        first = self.claim(request_id="req_alpha")
        second = self.claim(request_id="req_alpha")
        self.assertEqual(second.json["outcome"], admission.OUTCOME_REPLAYED)
        self.assertEqual(second.json["claim_token"], first.json["claim_token"])

    def test_lost_bind_response_replays_to_the_same_scan(self):
        """Scenario 7 -- the retry lands on already_bound, not a second row."""
        token = self.claim().json["claim_token"]
        payload = {"owner_user_id": OWNER, "request_id": "req_alpha",
                   "claim_token": token, "scan_id": SCAN_ID}
        self.assertEqual(self.post("/bind", payload).json["outcome"], admission.OUTCOME_BOUND)
        retry = self.post("/bind", payload)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json["outcome"], admission.OUTCOME_ALREADY_BOUND)

    def test_second_scan_id_cannot_be_bound(self):
        token = self.claim().json["claim_token"]
        self.post("/bind", {"owner_user_id": OWNER, "request_id": "req_alpha",
                            "claim_token": token, "scan_id": SCAN_ID})
        conflict = self.post("/bind", {"owner_user_id": OWNER, "request_id": "req_alpha",
                                       "claim_token": token, "scan_id": "6a7f518b619f437d8c363983"})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json["error"], admission.ERROR_SCAN_IDENTITY_CONFLICT)

    def test_forged_token_cannot_bind(self):
        self.claim()
        response = self.post("/bind", {"owner_user_id": OWNER, "request_id": "req_alpha",
                                       "claim_token": "tok_forged", "scan_id": SCAN_ID})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error"], admission.ERROR_INVALID_CLAIM_TOKEN)

    def test_same_request_different_fingerprint_conflicts(self):
        """Scenario 8, through HTTP."""
        self.claim(request_id="req_alpha")
        response = self.claim(request_id="req_alpha", fingerprint="standard_150|https://evil.example/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error"], admission.ERROR_REQUEST_CONFLICT)

    def test_release_requires_the_bound_scan(self):
        token = self.claim().json["claim_token"]
        self.post("/bind", {"owner_user_id": OWNER, "request_id": "req_alpha",
                            "claim_token": token, "scan_id": SCAN_ID})
        response = self.post("/release", {"owner_user_id": OWNER, "scan_id": "6a7f518b619f437d8c363983",
                                          "terminal_status": "failed"})
        self.assertEqual(response.status_code, 409)

    def test_release_rejects_a_non_terminal_status(self):
        token = self.claim().json["claim_token"]
        self.post("/bind", {"owner_user_id": OWNER, "request_id": "req_alpha",
                            "claim_token": token, "scan_id": SCAN_ID})
        response = self.post("/release", {"owner_user_id": OWNER, "scan_id": SCAN_ID,
                                          "terminal_status": "crawling"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error"], admission.ERROR_NOT_TERMINAL)

    def test_release_without_a_claim_is_not_found(self):
        response = self.post("/release", {"owner_user_id": OWNER, "scan_id": SCAN_ID,
                                          "terminal_status": "complete"})
        self.assertEqual(response.status_code, 404)

    def test_owners_do_not_share_admission(self):
        self.assertEqual(self.claim(owner=OWNER).status_code, 200)
        other = self.claim(owner="6a498da58ef5cec1f5cd4487", request_id="req_beta")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json["outcome"], admission.OUTCOME_CLAIMED)

    def test_each_fresh_claim_mints_a_distinct_token(self):
        first = self.claim(owner=OWNER).json["claim_token"]
        second = self.claim(owner="6a498da58ef5cec1f5cd4487").json["claim_token"]
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)


class TargetCooldown(CoordinatorTestCase):
    NOW = 1_800_000_000
    ORIGIN = "https://fixture.example:443"
    OTHER_OWNER = "other_owner"

    def setUp(self):
        super().setUp()
        self.now = self.NOW
        clock = patch.object(main.time, "time", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def claim_origin(self, origin=ORIGIN, *, owner=OWNER, request_id="req_alpha"):
        return self.post("/claim", {
            "owner_user_id": owner,
            "request_id": request_id,
            "request_fingerprint": FINGERPRINT,
            "target_origin": origin,
        })

    def bind_origin(self, origin=ORIGIN):
        claimed = self.claim_origin(origin)
        self.assertEqual(claimed.status_code, 200)
        bound = self.post("/bind", {
            "owner_user_id": OWNER, "request_id": "req_alpha",
            "claim_token": claimed.json["claim_token"], "scan_id": SCAN_ID,
        })
        self.assertEqual(bound.status_code, 200)
        return {
            "action": "observe_target_cooldown_v1", "status_code": 429,
            "owner_user_id": OWNER, "scan_id": SCAN_ID, "request_id": "req_alpha",
            "barrier_generation": claimed.json["barrier_generation"],
            "claim_sequence": claimed.json["claim_sequence"],
            "target_origin": self.ORIGIN,
            "observed_at": self.now, "retry_after_seconds": 3600,
        }

    def observe(self, payload, **options):
        return self.post("/observe-target-cooldown", payload, **options)

    def terminal_cooldown_payload(self, signal, status="complete"):
        return {
            "owner_user_id": signal["owner_user_id"],
            "scan_id": signal["scan_id"],
            "terminal_status": status,
            "target_cooldown": {
                **{key: signal[key] for key in ("request_id", "barrier_generation", "claim_sequence")},
                "observation": {
                    key: signal[key] for key in ("target_origin", "status_code", "observed_at", "retry_after_seconds")
                },
            },
        }

    def test_release_publishes_pending_observation_without_the_dedicated_relay(self):
        signal = self.bind_origin()
        payload = self.terminal_cooldown_payload(signal)
        self.now += 180
        released = self.post("/release-with-target-cooldown", payload)
        self.assertEqual(released.status_code, 200)
        self.assertEqual(released.json["outcome"], "released")
        self.assertEqual(released.json["target_cooldown_outcome"], "recorded")
        for owner in (OWNER, self.OTHER_OWNER):
            denied = self.claim_origin(owner=owner, request_id="fresh_request")
            self.assertEqual(denied.status_code, 429)
            self.assertEqual(denied.headers["Retry-After"], "3420")

        self.now += 30
        replay = self.post("/release-with-target-cooldown", payload)
        self.assertEqual(replay.json["outcome"], "already_released")
        self.assertEqual(replay.json["target_cooldown_outcome"], "unchanged")
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).headers["Retry-After"], "3390")
        self.assertEqual(self.claim_origin("https://other.example", request_id="new_origin").json["outcome"], "claimed")
        self.now = signal["observed_at"] + 3600
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["outcome"], "claimed")

    def test_bad_terminal_observation_cannot_release_or_change_cooldown(self):
        signal = self.bind_origin()
        before = {key: dict(value) for key, value in STORE.items()}
        payload = self.terminal_cooldown_payload(signal, status="limited")
        self.assertEqual(self.post("/release", payload).status_code, 400)
        variations = [
            ({"target_cooldown": {"observation": None}}, 400),
            ({"target_cooldown": {**payload["target_cooldown"], "claim_sequence": signal["claim_sequence"] + 1}}, 409),
            (self.terminal_cooldown_payload({**signal, "target_origin": "https://other.example:443"}), 409),
            (self.terminal_cooldown_payload({**signal, "status_code": "429"}), 400),
        ]
        for change, expected_status in variations:
            with self.subTest(change=change):
                response = self.post("/release-with-target-cooldown", {**payload, **change})
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(STORE, before)

    def test_expired_terminal_observation_releases_limited_scan_without_a_new_hold(self):
        signal = self.bind_origin()
        self.now = signal["observed_at"] + 3600
        released = self.post("/release-with-target-cooldown", self.terminal_cooldown_payload(signal, status="limited"))
        self.assertEqual(released.status_code, 200)
        self.assertEqual(released.json["target_cooldown_outcome"], "expired")
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["outcome"], "claimed")

    def test_verified_observation_blocks_fresh_claim_without_consuming_budget(self):
        signal = self.bind_origin("HTTPS://FIXTURE.example")
        recorded = self.observe(signal)
        self.assertEqual(recorded.status_code, 200)
        self.assertEqual(recorded.json, {"success": True, "outcome": "recorded"})
        store_before = {key: dict(value) for key, value in STORE.items()}

        denied = self.claim_origin("https://fixture.example", owner=self.OTHER_OWNER)
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(denied.json, {
            "success": False, "error": "target_cooldown_active", "retry_after_seconds": 3600,
        })
        self.assertEqual(denied.headers["Retry-After"], "3600")
        self.assertEqual(STORE, store_before)

        self.now += 3599
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["retry_after_seconds"], 1)
        self.now += 1
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["outcome"], "claimed")

    def test_fresh_claim_echoes_its_persisted_canonical_origin(self):
        claimed = self.claim_origin("HTTPS://FIXTURE.example")
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json.get("target_origin"), self.ORIGIN)
        self.assertEqual(STORE[f"scan_admission/{OWNER}"]["target_origin"], self.ORIGIN)
        self.assertNotIn("target_origin", claimed.json["cohort_evidence"])

    def test_legacy_claim_and_exact_replay_during_cooldown(self):
        signal = self.bind_origin()
        self.assertEqual(self.observe(signal).status_code, 200)
        replayed = self.claim_origin().json
        self.assertEqual(replayed["outcome"], "replayed")
        self.assertEqual(replayed["target_origin"], self.ORIGIN)
        self.assertEqual(self.claim().json["target_origin"], self.ORIGIN)
        legacy = self.claim(owner=self.OTHER_OWNER).json
        self.assertEqual(legacy["outcome"], "claimed")
        self.assertNotIn("target_origin", legacy)
        mixed_replay = self.claim_origin(owner=self.OTHER_OWNER).json
        self.assertEqual(mixed_replay["outcome"], "replayed")
        self.assertNotIn("target_origin", mixed_replay)
        self.assertEqual(self.claim_origin("https://www.fixture.example").json["error"], "request_conflict")

    def test_named_public_pilot_binds_fresh_and_replayed_claims_to_the_launcher_build(self):
        build = "a" * 64
        key = "scan_admission_control/global"
        request = {"owner_user_id": OWNER, "request_id": "published_pilot_req01", "request_fingerprint": FINGERPRINT}
        signed_request = {**request, "pilot_launcher_build_id": build}
        self.assertEqual(self.post("/claim", signed_request).status_code, 423)
        STORE[key] = {
            "mode": "acceptance_only", "generation": 2, "claim_sequence": 0,
            "acceptance": {
                "cohort_id": "cohort_fixture", "release_id": "release_fixture", "source_sha": "a" * 40,
                "owner_allowlist": [OWNER], "expires_at": self.NOW + 600,
                "total_claim_budget": 1, "per_owner_claim_budget": 1, "required_launcher_build_id": build,
                "total_claims_used": 0, "owner_claims_used": {},
            },
        }
        before = deepcopy(STORE)
        for unsafe in [request, {**request, "pilot_launcher_build_id": "b" * 64}]:
            self.assertEqual(self.post("/claim", unsafe).status_code, 423)
            self.assertEqual(STORE, before)
        allowed = self.post("/claim", signed_request)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json["pilot_launcher_build_id"], build)
        self.assertEqual(STORE[key]["acceptance"]["total_claims_used"], 1)
        after = deepcopy(STORE)
        self.assertEqual(self.post("/claim", request).status_code, 423)
        self.assertEqual(self.post("/claim", signed_request).json["outcome"], "replayed")
        self.assertEqual(STORE, after)

    def test_cooldown_refusal_leaves_acceptance_budget_untouched(self):
        signal = self.bind_origin()
        self.assertEqual(self.observe({**signal, "retry_after_seconds": 30}).json["outcome"], "recorded")
        key = "scan_admission_control/global"
        STORE[key] = {
            **STORE[key], "mode": "acceptance_only", "generation": 2,
            "acceptance": {
                "cohort_id": "cohort_fixture", "release_id": "release_fixture", "source_sha": "a" * 40,
                "owner_allowlist": [self.OTHER_OWNER], "expires_at": self.NOW + 600,
                "total_claim_budget": 1, "per_owner_claim_budget": 1,
                "total_claims_used": 0, "owner_claims_used": {},
            },
        }
        before = deepcopy(STORE)
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["error"], "target_cooldown_active")
        self.assertEqual(STORE, before)

        self.now += 30
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["outcome"], "claimed")
        self.assertEqual(STORE[key]["acceptance"]["owner_claims_used"], {self.OTHER_OWNER: 1})
        self.assertEqual(STORE[key]["acceptance"]["total_claims_used"], 1)

    def test_exhausted_acceptance_does_not_disclose_cooldown(self):
        signal = self.bind_origin()
        self.assertEqual(self.observe(signal).json["outcome"], "recorded")
        key = "scan_admission_control/global"
        STORE[key] = {
            **STORE[key], "mode": "acceptance_only", "generation": 2,
            "acceptance": {
                "cohort_id": "cohort_fixture", "release_id": "release_fixture", "source_sha": "a" * 40,
                "owner_allowlist": [self.OTHER_OWNER], "expires_at": self.NOW + 600,
                "total_claim_budget": 1, "per_owner_claim_budget": 1,
                "total_claims_used": 1, "owner_claims_used": {self.OTHER_OWNER: 1},
            },
        }
        before = deepcopy(STORE)
        denied = self.claim_origin(owner=self.OTHER_OWNER)
        self.assertEqual(denied.json, {"success": False, "error": "scan_intake_paused"})
        self.assertEqual(denied.status_code, 423)
        self.assertEqual(STORE, before)

    def test_cooldown_read_failure_only_rejects_fresh_target_aware_claims(self):
        signal = self.bind_origin()
        self.assertEqual(self.observe(signal).json["outcome"], "recorded")
        before = deepcopy(STORE)
        get = FakeDocumentRef.get

        def unavailable(ref, transaction=None):
            if ref.key.startswith("scan_target_cooldowns/"):
                raise RuntimeError("Firestore read interrupted")
            return get(ref, transaction=transaction)

        with patch.object(FakeDocumentRef, "get", unavailable):
            failed = self.claim_origin(owner=self.OTHER_OWNER)
            self.assertEqual(failed.status_code, 503)
            self.assertEqual(failed.json["error"], "coordinator_unavailable")
            self.assertEqual(self.claim_origin().json["outcome"], "replayed")
            self.assertEqual(STORE, before)
            self.assertEqual(self.claim(owner=self.OTHER_OWNER).json["outcome"], "claimed")

    def test_origin_cooldown_does_not_imply_an_alias(self):
        self.assertEqual(self.observe(self.bind_origin()).status_code, 200)
        independent = ("http://fixture.example", "https://www.fixture.example",
                       "https://fixture.example:8443", "https://other.example", "https://fixture.example.")
        for index, origin in enumerate(independent):
            with self.subTest(origin=origin):
                self.assertEqual(self.claim_origin(origin, owner=f"owner{index}").json["outcome"], "claimed")

    def test_observation_requires_exact_live_claim(self):
        observation = self.bind_origin()
        store_before = {key: dict(value) for key, value in STORE.items()}
        for changed in (
            {"target_origin": "https://www.fixture.example"},
            {"request_id": "old_request"},
            {"owner_user_id": "wrong_owner"},
            {"scan_id": "old_scan"},
            {"barrier_generation": observation["barrier_generation"] + 1},
            {"claim_sequence": observation["claim_sequence"] + 1},
        ):
            with self.subTest(changed=changed):
                rejected = self.observe({**observation, **changed})
                self.assertEqual(rejected.status_code, 409)
                self.assertEqual(rejected.json["error"], "target_cooldown_claim_conflict")
                self.assertEqual(STORE, store_before)

        released = self.post("/release", {
            "owner_user_id": OWNER, "scan_id": SCAN_ID, "terminal_status": "complete",
        })
        self.assertEqual(released.status_code, 200)
        self.assertEqual(self.observe(observation).status_code, 409)

    def test_observation_authentication_and_retry_after_validation(self):
        observation = self.bind_origin()
        store_before = {key: dict(value) for key, value in STORE.items()}
        self.assertEqual(self.observe(observation, signature="00" * 32).status_code, 401)
        for changed in (
            {"action": "release"}, {"status_code": 503}, {"status_code": "429"},
            {"observed_at": self.NOW + 301}, {"observed_at": True},
            {"retry_after_seconds": 0}, {"retry_after_seconds": -1}, {"retry_after_seconds": "3600"},
            {"retry_after_seconds": True}, {"retry_after_seconds": 0.5},
            {"target_origin": "https://fixture.example/resource"},
            {"terminal_status": "complete"},
        ):
            with self.subTest(changed=changed):
                self.assertEqual(self.observe({**observation, **changed}).status_code, 400)
                self.assertEqual(STORE, store_before)

    def test_observations_are_bounded_and_max_update_uses_original_timestamp(self):
        observation = self.bind_origin()
        expired = {**observation, "retry_after_seconds": 1}
        self.now += 2
        self.assertEqual(self.observe(expired).json["outcome"], "expired")

        long = {**observation, "retry_after_seconds": 100_000}
        self.assertEqual(self.observe(long).json["outcome"], "recorded")
        self.now += 10
        self.assertEqual(self.observe(long).json["outcome"], "unchanged")
        self.assertEqual(self.observe({**observation, "retry_after_seconds": 120}).json["outcome"], "unchanged")
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["retry_after_seconds"], 86_388)

        later = {**long, "observed_at": self.now}
        self.assertEqual(self.observe(later).json["outcome"], "recorded")
        self.assertEqual(self.claim_origin(owner=self.OTHER_OWNER).json["retry_after_seconds"], 86_400)

    def test_invalid_claim_origins_do_not_allocate_an_owner_slot(self):
        for origin in (None, "", True, "https://fixture.example/other", "https://a@fixture.example",
                       "https://fixture.example?x=1", "https://fixture.example:65536",
                       "http://10.0.0.1", "https://[::1]", "https://[93.184.216.34]",
                       "https://fixture.example\n"):
            with self.subTest(origin=origin):
                response = self.claim_origin(origin)
                self.assertEqual(response.json, {"success": False, "error": "invalid_target_origin"})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(STORE)


class PublishedPilotAcceptance(CoordinatorTestCase):
    def test_named_500_transitions_do_not_need_a_global_drain_snapshot(self):
        source = "1" * 40
        public_count = control.MAX_INTERNAL_OBLIGATIONS + 1
        key = f"{main.CONTROL_COLLECTION}/{main.CONTROL_DOCUMENT}"
        STORE[key] = {"mode": "open", "generation": 4, "claim_sequence": public_count}
        for index in range(public_count):
            public_owner = f"public_customer_{index}"
            STORE[f"{main.COLLECTION}/{public_owner}"] = {
                "owner_user_id": public_owner, "state": "bound", "admission_mode": "open",
                "request_id": f"public_request_{index}", "scan_id": f"public_scan_{index}",
                "barrier_generation": 4, "claim_sequence": index + 1,
            }
        context = {"reason": "Test named pilot under public load", "change_ticket": "test-pilot-load"}
        definition = {
            "cohort_id": "published_500", "release_id": "paid_candidate",
            "source_sha": source, "owner_user_ids": [OWNER], "expires_at": int(time.time()) + 900,
            "total_claim_budget": 1, "per_owner_claim_budget": 1, "required_launcher_build_id": "a" * 64,
        }
        with patch.object(main, "SOURCE_SHA", source):
            started = self.operator_post("/ops/barrier/pilot-500/start", {
                **context, "operation": "start_500_pilot", "acceptance": definition,
                "intended_prior": {"mode": "open", "generation": 4},
            })
            self.assertEqual(started.status_code, 200, started.json)
            held = self.operator_post("/ops/barrier/pilot-500/hold", {
                **context, "operation": "hold_500_pilot", "cohort_id": definition["cohort_id"],
                "intended_prior": {"mode": "open", "generation": 5},
            })
            self.assertEqual(held.status_code, 200, held.json)
        for response, state, generation in [(started, "configured", 5), (held, "held", 6)]:
            self.assertNotIn("drain_snapshot", response.json)
            snapshot = response.json["pilot_snapshot"]
            proof = snapshot.pop("proof")
            self.assertTrue(control.verify_record(OPERATOR_SIGNING_ROOT, control.SNAPSHOT_LABEL, snapshot, proof))
            self.assertEqual(snapshot["version"], "admission_published_500_pilot_snapshot_v1")
            self.assertEqual(snapshot["barrier"]["mode"], "open")
            self.assertEqual(snapshot["barrier"]["generation"], generation)
            self.assertEqual(snapshot["boundary"]["published_500_pilot"]["state"], state)
            self.assertIs(snapshot["drain_ready"], False)
            self.assertNotIn("counts", snapshot)
        self.assertEqual(STORE[key]["claim_sequence"], public_count)
        status = self.operator_post("/ops/barrier/status", {
            **context, "operation": "status", "expected_generation": 6,
        })
        self.assertEqual(status.status_code, 409, status.json)
        self.assertEqual(status.json["error"], "drain_snapshot_capacity_exceeded")
        self.assertEqual(self.claim(owner="another_public_customer").json["admission_mode"], "open")

    def test_named_500_pilot_can_start_and_hold_while_public_claims_continue(self):
        source = "1" * 40
        build = "a" * 64
        key = f"{main.CONTROL_COLLECTION}/{main.CONTROL_DOCUMENT}"
        STORE[key] = {"mode": "open", "generation": 4, "claim_sequence": 0}
        baseline = self.claim(owner="public_customer_1").json
        self.assertEqual(baseline["admission_mode"], "open")
        definition = {
            "cohort_id": "published_500", "release_id": "paid_candidate",
            "source_sha": source, "owner_user_ids": [OWNER],
            "expires_at": int(time.time()) + 900,
            "total_claim_budget": 1, "per_owner_claim_budget": 1,
            "required_launcher_build_id": build,
        }
        operator_context = {"reason": "Test equivalent 150 and 500 admission", "change_ticket": "test-concurrent"}
        operator_payload = {
            **operator_context, "operation": "start_500_pilot",
            "intended_prior": {"mode": "open", "generation": 4}, "acceptance": definition,
        }
        pilot_request = {
            "owner_user_id": OWNER, "request_id": "published_500_req_1", "request_fingerprint": FINGERPRINT,
            "pilot_launcher_build_id": build, "pilot_page_cap": 500,
        }
        with patch.object(main, "SOURCE_SHA", source):
            self.assertEqual(self.post("/claim", pilot_request).status_code, 423)
            started = self.operator_post("/ops/barrier/pilot-500/start", operator_payload)
            self.assertEqual(started.status_code, 200, started.json)
            self.assertEqual(started.json["barrier"]["mode"], "open")
            self.assertEqual(started.json["pilot_snapshot"]["boundary"]["published_500_pilot"]["page_cap"], 500)
            self.assertEqual(self.operator_post("/ops/barrier/pilot-500/start", operator_payload).status_code, 409)
            for refusal, status in [
                ({"owner_user_id": "unlisted_customer"}, 423),
                ({"pilot_launcher_build_id": "b" * 64}, 423),
                ({"pilot_page_cap": 150}, 400),
            ]:
                self.assertEqual(self.post("/claim", {**pilot_request, **refusal}).status_code, status)
            self.assertEqual(self.claim(owner="public_customer_2").json["admission_mode"], "open")
            replay_only = {**pilot_request, "pilot_replay_only": True}
            self.assertEqual(self.post("/claim", replay_only).status_code, 423)
            self.assertEqual(STORE[key]["published_500_pilot"]["total_claims_used"], 0)
            with patch.object(main, "SOURCE_SHA", "2" * 40):
                self.assertEqual(self.post("/claim", pilot_request).status_code, 423)
            admitted = self.post("/claim", pilot_request)
            self.assertEqual(admitted.status_code, 200, admitted.json)
            self.assertEqual(admitted.json["admission_mode"], "acceptance_only")
            self.assertEqual(admitted.json["pilot_page_cap"], 500)
            self.assertEqual(STORE[key]["published_500_pilot"]["total_claims_used"], 1)
            self.assertEqual(self.claim(request_id="public_same_owner").status_code, 429)
            hold_payload = {
                **operator_context, "operation": "hold_500_pilot", "cohort_id": "published_500",
                "intended_prior": {"mode": "open", "generation": started.json["barrier"]["generation"]},
            }
            self.assertEqual(self.operator_post("/ops/barrier/pilot-500/hold",
                                                {**hold_payload, "cohort_id": "another_pilot"}).status_code, 409)
            held = self.operator_post("/ops/barrier/pilot-500/hold", hold_payload)
            self.assertEqual(held.status_code, 200, held.json)
            self.assertEqual(held.json["barrier"]["mode"], "open")
            self.assertEqual(held.json["pilot_snapshot"]["boundary"]["published_500_pilot"]["state"], "held")
            replay = self.post("/claim", replay_only)
            self.assertEqual(replay.json["outcome"], "replayed")
            self.assertEqual(replay.json["pilot_page_cap"], 500)
            self.assertEqual(self.post("/claim", {**replay_only, "request_id": "another_500_request"}).status_code, 423)
            self.assertEqual(self.claim(owner="public_customer_3").json["admission_mode"], "open")
        bound = self.post("/bind", {
            "owner_user_id": OWNER, "request_id": pilot_request["request_id"],
            "claim_token": admitted.json["claim_token"], "scan_id": SCAN_ID,
        })
        self.assertEqual(bound.status_code, 200, bound.json)

    def test_opening_the_pilot_requires_exact_source_and_attests_the_launcher(self):
        source = "1" * 40
        launcher = "a" * 64
        key = f"{main.CONTROL_COLLECTION}/{main.CONTROL_DOCUMENT}"
        STORE[key] = {"mode": "closed", "generation": 4, "claim_sequence": 0}
        path = "/ops/barrier/acceptance-only"
        acceptance = {
            "cohort_id": "public_pilot_150", "release_id": "public_candidate",
            "source_sha": source, "owner_user_ids": [OWNER],
            "expires_at": int(time.time()) + 900, "total_claim_budget": 1, "per_owner_claim_budget": 1,
        }
        payload = {
            "operation": "published_pilot_acceptance", "reason": "test published pilot",
            "change_ticket": "test-150", "intended_prior": {"mode": "closed", "generation": 4},
            "acceptance": acceptance,
        }
        with patch.object(main, "SOURCE_SHA", source):
            missing = self.operator_post(path, payload)
            self.assertEqual(missing.status_code, 400)
            self.assertEqual(missing.json["error"], "invalid_acceptance_launcher_build_id")
            acceptance["required_launcher_build_id"] = launcher
            wrong_source = {**payload, "acceptance": {**acceptance, "source_sha": "2" * 40}}
            stale = self.operator_post(path, wrong_source)
            self.assertEqual(stale.status_code, 409)
            self.assertEqual(stale.json["error"], "acceptance_source_mismatch")
            self.assertEqual(STORE[key]["mode"], "closed")
            response = self.operator_post(path, payload)

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["operation"], "acceptance_only")
        self.assertEqual(STORE[key]["acceptance"]["required_launcher_build_id"], launcher)
        snapshot = response.json["drain_snapshot"]
        proof = snapshot.pop("proof")
        self.assertEqual(snapshot["boundary"]["required_launcher_build_id"], launcher)
        self.assertTrue(control.verify_record(OPERATOR_SIGNING_ROOT, control.SNAPSHOT_LABEL, snapshot, proof))


class StatusSurface(CoordinatorTestCase):
    def test_status_reports_an_active_lease_without_the_token(self):
        self.claim()
        response = self.post("/status", {"owner_user_id": OWNER})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["lease_active"])
        self.assertNotIn("claim_token", response.json["admission"])
        self.assertNotIn("request_fingerprint", response.json["admission"])

    def test_status_on_an_unknown_owner_is_empty(self):
        response = self.post("/status", {"owner_user_id": "6a498da58ef5cec1f5cd4499"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["lease_active"])
        self.assertEqual(response.json["admission"]["state"], "")


class AuthenticationRejectionLogging(CoordinatorTestCase):
    """A 401 must say why in the log, not only in the response body.

    The coordinator used to reject every request in silence. Cloud Logging then
    showed nothing for a service that was running and answering 401, and that
    empty log was read as proof the request had never arrived -- sending an
    outage investigation after the network path for days. These tests pin the
    rejection log so that silence can never be mistaken for absence again.
    """

    def rejecting(self, send):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            response = send()
        entries = [
            json.loads(line)
            for line in buffer.getvalue().splitlines()
            if line.startswith("{")
        ]
        rejections = [e for e in entries if e.get("event") == "admission_auth_rejected"]
        self.assertEqual(len(rejections), 1, buffer.getvalue())
        return response, rejections[0]

    def test_invalid_signature_is_logged_with_discriminators(self):
        response, entry = self.rejecting(
            lambda: self.post("/claim", {"owner_user_id": OWNER}, signature="ab" * 32)
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(entry["reason"], "invalid_signature")
        self.assertEqual(entry["severity"], "WARNING")
        self.assertEqual(entry["path"], "/claim")
        self.assertEqual(entry["auth_label"], "fixlist-admission-coordinator-v1")
        self.assertTrue(entry["signature_present"])
        self.assertEqual(entry["signature_length"], 64)
        self.assertGreater(entry["body_bytes"], 0)

    def test_operator_leg_is_named_separately_from_the_base44_leg(self):
        # The operator leg is only reached once the Google identity check passes,
        # and the module reads its audience and service account from the ambient
        # environment via setdefault. A runner that already exports either of
        # them -- the release workflow exports the audience -- leaves the module
        # holding one value while this file's constants hold another, and the
        # request is refused at the identity check before the HMAC layer under
        # test runs at all. Binding the claims to whatever the module actually
        # loaded makes the test assert on the signature boundary either way.
        verifier = main.OPERATOR_TOKEN_VERIFIER
        main.OPERATOR_TOKEN_VERIFIER = lambda _token, _audience: {
            "iss": "https://accounts.google.com",
            "aud": main.OPERATOR_AUDIENCE,
            "email": main.OPERATOR_SERVICE_ACCOUNT,
            "email_verified": True,
        }
        try:
            _response, entry = self.rejecting(
                lambda: self.operator_post("/ops/barrier/status", {}, root="wrong-operator-root")
            )
        finally:
            main.OPERATOR_TOKEN_VERIFIER = verifier
        self.assertEqual(entry["reason"], "invalid_signature")
        self.assertEqual(entry["auth_label"], "fixlist-admission-operator-v1")

    def test_missing_signature_is_logged_as_absent(self):
        def send():
            return self.client.post(
                "/claim",
                data=b"{}",
                headers={
                    "content-type": "application/json",
                    "x-fixlist-timestamp": str(int(time.time())),
                },
            )

        _response, entry = self.rejecting(send)
        self.assertEqual(entry["reason"], "invalid_signature")
        self.assertFalse(entry["signature_present"])
        self.assertEqual(entry["signature_length"], 0)

    def test_stale_request_logs_the_measured_skew(self):
        stamp = str(int(time.time()) - (main.MAX_CLOCK_SKEW_SECONDS + 120))
        response, entry = self.rejecting(
            lambda: self.post("/claim", {"owner_user_id": OWNER}, timestamp=stamp)
        )
        self.assertEqual(response.json["error"], "stale_request")
        self.assertEqual(entry["reason"], "stale_request")
        self.assertEqual(entry["max_clock_skew_seconds"], main.MAX_CLOCK_SKEW_SECONDS)
        # The measured skew is what tells an operator a clock is wrong rather
        # than a key, so it has to be the real number, not a boolean.
        self.assertAlmostEqual(entry["skew_seconds"], main.MAX_CLOCK_SKEW_SECONDS + 120, delta=5)

    def test_invalid_timestamp_is_logged(self):
        response, entry = self.rejecting(
            lambda: self.post("/claim", {"owner_user_id": OWNER}, timestamp="not-a-number")
        )
        self.assertEqual(response.json["error"], "invalid_timestamp")
        self.assertEqual(entry["reason"], "invalid_timestamp")
        self.assertTrue(entry["timestamp_present"])

    def test_a_whitespace_bearing_root_names_the_unquoted_env_file_round_trip(self):
        """The exact shape that breaks the Base44 leg must be reported by name.

        Cloud Run injects a secret payload verbatim, so a version ending in a
        newline reaches this service with that newline. The former unquoted env
        entry dropped it, so a peer configured from that entry signed with the
        stripped root. Both sides then believed they held "the" signing key and
        every call returned a 401.
        """
        body = json.dumps({"owner_user_id": OWNER}).encode("utf-8")
        stamp = str(int(time.time()))
        stripped_signature = sign(body, stamp, root=SIGNING_ROOT)
        original = main.SIGNING_ROOT
        main.SIGNING_ROOT = SIGNING_ROOT + "\n"
        try:
            response, entry = self.rejecting(
                lambda: self.post("/claim", None, raw=body, timestamp=stamp, signature=stripped_signature)
            )
        finally:
            main.SIGNING_ROOT = original
        self.assertEqual(response.status_code, 401)
        self.assertEqual(entry["reason"], "invalid_signature")
        self.assertTrue(entry["root_has_surrounding_whitespace"])
        self.assertTrue(entry["matches_whitespace_stripped_root"])

    def test_a_clean_root_reports_no_whitespace_diagnosis(self):
        """The diagnosis is computed only when this service's own root is
        affected, so a forged signature against a clean root discloses nothing
        about what the caller signed with."""
        _response, entry = self.rejecting(
            lambda: self.post("/claim", {"owner_user_id": OWNER}, signature="cd" * 32)
        )
        self.assertNotIn("root_has_surrounding_whitespace", entry)
        self.assertNotIn("matches_whitespace_stripped_root", entry)

    def test_rejection_log_never_carries_signing_material(self):
        body = json.dumps({"owner_user_id": OWNER, "request_id": "req_secret_body"}).encode("utf-8")
        stamp = str(int(time.time()))
        supplied = "ef" * 32
        expected = sign(body, stamp)
        _response, entry = self.rejecting(
            lambda: self.post("/claim", None, raw=body, timestamp=stamp, signature=supplied)
        )
        serialized = json.dumps(entry)
        for forbidden in (SIGNING_ROOT, OPERATOR_SIGNING_ROOT, supplied, expected, "req_secret_body"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
