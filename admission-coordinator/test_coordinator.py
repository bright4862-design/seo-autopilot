"""HTTP-surface coverage for the admission coordinator.

Firestore is replaced with an in-process fake so the transaction wiring, the
HMAC boundary and the full claim/bind/release lifecycle are provable without a
network, an emulator or credentials. The fake is installed into ``sys.modules``
before ``main`` is imported, because ``main`` binds ``firestore`` at import time.
"""

import contextlib
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
    "aud": OPERATOR_AUDIENCE,
    "email": OPERATOR_SERVICE_ACCOUNT,
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

    def test_a_whitespace_bearing_root_names_the_env_file_round_trip(self):
        """The exact shape that breaks the Base44 leg must be reported by name.

        Cloud Run injects a secret payload verbatim, so a version ending in a
        newline reaches this service with that newline. An env file cannot carry
        it, so a peer configured from one signs with the stripped root. Both
        sides then believe they hold "the" signing key and every call 401s.
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
