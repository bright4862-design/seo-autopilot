import base64
from copy import deepcopy
import hashlib
import hmac
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

# Local tests use canonical repo sources. The production Docker context places
# the same exact committed modules in /app/app without importing the worker.
SCANNER_ROOT = Path(__file__).resolve().parents[1] / "scanner-api"
if SCANNER_ROOT.is_dir():
    sys.path.insert(0, str(SCANNER_ROOT))

os.environ.setdefault(
    "SCAN_TASKS_QUEUE_PATH",
    "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150",
)
os.environ.setdefault(
    "SCAN_DRAIN_QUEUE_PATH",
    "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150-drain",
)
os.environ.setdefault(
    "SCAN_WORKER_URL",
    "https://fixlist-standard150-worker-tpucgyfewa-ew.a.run.app/scan-job",
)
os.environ.setdefault(
    "TASKS_INVOKER_SERVICE_ACCOUNT",
    "fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com",
)
os.environ.setdefault("SCAN_EVIDENCE_SIGNING_KEY", "unit-test-signing-root")

for module_name in ("google.cloud.firestore", "google.cloud", "google"):
    sys.modules.pop(module_name, None)

spec = importlib.util.spec_from_file_location(
    "fixlist_dispatch_gateway_main",
    Path(__file__).with_name("main.py"),
)
assert spec and spec.loader
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)


def encoded(value):
    return base64.b64encode(json.dumps(value).encode("utf-8")).decode("ascii")


def task(*, scan_id="scan_abc123", drain=False, attempt=1, respect_robots_txt=True, owner_override=False):
    short_name = f"standard150-{'drain-' if drain else ''}{scan_id}-a{attempt}"
    job = {
        "scan_id": scan_id,
        "request_id": "req_abc123",
        "website_url": "https://example.com/",
    }
    if drain:
        job["drain_after"] = "2099-01-01T00:00:00.000Z"
    else:
        job.update({
            "scan_mode": "standard_150",
            "respect_robots_txt": respect_robots_txt,
            "owner_attested_robots_override": owner_override,
        })

    value = {
        "name": f"{main.DRAIN_QUEUE_PATH if drain else main.QUEUE_PATH}/tasks/{short_name}",
        "dispatchDeadline": "480s",
        "httpRequest": {
            "url": main.DRAIN_URL if drain else main.WORKER_URL,
            "httpMethod": "POST",
            "headers": {"content-type": "application/json"},
            "body": encoded(job),
            "oidcToken": {
                "serviceAccountEmail": main.INVOKER_SA,
                "audience": main.WORKER_ORIGIN,
            },
        },
    }
    if drain:
        value["scheduleTime"] = "2099-01-01T00:00:00.000Z"
    return value


class ValidateDispatchTests(unittest.TestCase):
    def validate(self, value, *, queue_path=None):
        inferred_queue = main.DRAIN_QUEUE_PATH if "standard150-drain-" in str(value.get("name") or "") else main.QUEUE_PATH
        return main.validate_dispatch({
            "queue_path": queue_path or inferred_queue,
            "task": value,
        })

    def assertRejected(self, value, expected):
        accepted, error = self.validate(value)
        self.assertIsNone(accepted)
        self.assertEqual(error, expected)

    def test_exact_scan_task_is_accepted(self):
        accepted, error = self.validate(task())
        self.assertIsNone(error)
        self.assertIsNotNone(accepted)

    def test_owner_override_pair_is_accepted(self):
        accepted, error = self.validate(task(respect_robots_txt=False, owner_override=True))
        self.assertIsNone(error)
        self.assertIsNotNone(accepted)

    def test_non_owner_pair_is_accepted(self):
        accepted, error = self.validate(task(respect_robots_txt=True, owner_override=False))
        self.assertIsNone(error)
        self.assertIsNotNone(accepted)

    def test_mismatched_or_missing_robots_policy_is_rejected(self):
        for value in (
            task(respect_robots_txt=False, owner_override=False),
            task(respect_robots_txt=True, owner_override=True),
        ):
            self.assertRejected(value, "robots_policy_pair")
        missing = task()
        job = json.loads(base64.b64decode(missing["httpRequest"]["body"]))
        del job["owner_attested_robots_override"]
        missing["httpRequest"]["body"] = encoded(job)
        self.assertRejected(missing, "robots_policy_missing")

    def test_exact_drain_task_is_accepted(self):
        accepted, error = self.validate(task(drain=True))
        self.assertIsNone(error)
        self.assertIsNotNone(accepted)

    def test_scan_task_cannot_use_drain_queue(self):
        accepted, error = self.validate(task(), queue_path=main.DRAIN_QUEUE_PATH)
        self.assertIsNone(accepted)
        self.assertEqual(error, "invalid_task_name")

    def test_drain_task_cannot_use_scan_queue(self):
        accepted, error = self.validate(task(drain=True), queue_path=main.QUEUE_PATH)
        self.assertIsNone(accepted)
        self.assertEqual(error, "invalid_task_name")

    def test_wrong_queue_is_rejected(self):
        accepted, error = main.validate_dispatch({
            "queue_path": "projects/other/locations/europe-west1/queues/other",
            "task": task(),
        })
        self.assertIsNone(accepted)
        self.assertEqual(error, "invalid_queue")

    def test_task_name_must_be_deterministic(self):
        value = task()
        value["name"] = f"{main.QUEUE_PATH}/tasks/arbitrary"
        self.assertRejected(value, "invalid_task_name")

    def test_scan_identity_must_match_task_name(self):
        value = task(scan_id="scan_abc123")
        job = json.loads(base64.b64decode(value["httpRequest"]["body"]))
        job["scan_id"] = "scan_other"
        value["httpRequest"]["body"] = encoded(job)
        self.assertRejected(value, "scan_identity_mismatch")

    def test_scan_task_cannot_target_drain_route(self):
        value = task()
        value["httpRequest"]["url"] = main.DRAIN_URL
        self.assertRejected(value, "invalid_worker_target")

    def test_drain_task_cannot_target_scan_route(self):
        value = task(drain=True)
        value["httpRequest"]["url"] = main.WORKER_URL
        self.assertRejected(value, "invalid_worker_target")

    def test_wrong_invoker_is_rejected(self):
        value = task()
        value["httpRequest"]["oidcToken"]["serviceAccountEmail"] = "other@example.com"
        self.assertRejected(value, "invalid_invoker")

    def test_wrong_audience_is_rejected(self):
        value = task()
        value["httpRequest"]["oidcToken"]["audience"] = "https://example.com"
        self.assertRejected(value, "invalid_audience")

    def test_wrong_dispatch_deadline_is_rejected(self):
        value = task()
        value["dispatchDeadline"] = "300s"
        self.assertRejected(value, "invalid_dispatch_deadline")

    def test_scan_mode_is_pinned(self):
        value = task()
        job = json.loads(base64.b64decode(value["httpRequest"]["body"]))
        job["scan_mode"] = "premium_5000"
        value["httpRequest"]["body"] = encoded(job)
        self.assertRejected(value, "invalid_scan_mode")

    def test_scan_task_cannot_be_scheduled(self):
        value = task()
        value["scheduleTime"] = "2099-01-01T00:00:00.000Z"
        self.assertRejected(value, "unexpected_scan_schedule")

    def test_drain_requires_schedule_time(self):
        value = task(drain=True)
        del value["scheduleTime"]
        self.assertRejected(value, "missing_drain_schedule")

    def test_drain_requires_drain_after(self):
        value = task(drain=True)
        job = json.loads(base64.b64decode(value["httpRequest"]["body"]))
        del job["drain_after"]
        value["httpRequest"]["body"] = encoded(job)
        self.assertRejected(value, "missing_drain_after")


class SignatureTests(unittest.TestCase):
    def test_signature_is_bound_to_timestamp_and_body(self):
        timestamp = str(int(time.time()))
        body = b'{"queue_path":"q","task":null}'
        signature = main._expected_signature(timestamp, body)
        self.assertRegex(signature, r"^[0-9a-f]{64}$")
        self.assertNotEqual(signature, main._expected_signature(str(int(timestamp) + 1), body))
        self.assertNotEqual(signature, main._expected_signature(timestamp, body + b" "))

    def test_health_contract(self):
        client = main.app.test_client()
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["service"], "fixlist-dispatch-gateway")
        self.assertEqual(payload["queue"], main.QUEUE_PATH)
        self.assertEqual(payload["drain_queue"], main.DRAIN_QUEUE_PATH)
        self.assertEqual(payload["worker_origin"], main.WORKER_ORIGIN)

    def test_dispatch_rejects_oversized_body_before_auth(self):
        client = main.app.test_client()
        response = client.post(
            "/dispatch",
            data=b"x" * (main.MAX_DISPATCH_BODY_BYTES + 1),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error"], "request_too_large")

    def test_dispatch_rejects_missing_timestamp_before_cloud_auth(self):
        client = main.app.test_client()
        response = client.post("/dispatch", json={"queue_path": main.QUEUE_PATH, "task": task()})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "invalid_timestamp")

    def test_dispatch_rejects_stale_request_before_cloud_auth(self):
        client = main.app.test_client()
        raw = json.dumps({"queue_path": main.QUEUE_PATH, "task": task()}, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()) - main.MAX_CLOCK_SKEW_SECONDS - 1)
        signature = main._expected_signature(timestamp, raw)
        response = client.post(
            "/dispatch",
            data=raw,
            headers={
                "content-type": "application/json",
                "x-fixlist-timestamp": timestamp,
                "x-fixlist-signature": signature,
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "stale_request")

    def test_dispatch_rejects_bad_signature_before_cloud_auth(self):
        client = main.app.test_client()
        timestamp = str(int(time.time()))
        response = client.post(
            "/dispatch",
            json={"queue_path": main.QUEUE_PATH, "task": task()},
            headers={
                "x-fixlist-timestamp": timestamp,
                "x-fixlist-signature": "0" * 64,
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "invalid_signature")


class RobotsDiagnosticsTests(unittest.TestCase):
    def signed_post(self, value, *, valid_signature=True):
        raw = json.dumps({"queue_path": main.QUEUE_PATH, "task": value}).encode()
        timestamp = str(int(time.time()))
        return main.app.test_client().post("/dispatch", data=raw, headers={
            "content-type": "application/json",
            "x-fixlist-timestamp": timestamp,
            "x-fixlist-signature": main._expected_signature(timestamp, raw) if valid_signature else "0" * 64,
        })

    def test_signed_rejections_are_precise_safe_and_never_enqueue(self):
        cases = []
        fields = ("respect_robots_txt", "owner_attested_robots_override")
        for absent in ((fields[0],), (fields[1],), fields):
            cases.append(({field: True for field in fields if field not in absent}, "robots_policy_missing", 422))
        for field in fields:
            for bad in (None, 0, 1, 0.0, 1.0, "false", "true", "", [], {}):
                policy = dict(zip(fields, (False, True)))
                policy[field] = bad
                cases.append((policy, "robots_policy_type", 400))
        for flag in (False, True):
            cases.append((dict.fromkeys(fields, flag), "robots_policy_pair", 412))
        with patch.object(main.google.auth, "default") as auth, patch.object(main.requests, "post") as enqueue:
            for policy, code, status in cases:
                with self.subTest(policy=policy):
                    value = task()
                    job = json.loads(base64.b64decode(value["httpRequest"]["body"]))
                    for field in fields:
                        del job[field]
                    job.update(policy)
                    job["private_evidence"] = "must-not-appear"
                    value["httpRequest"]["body"] = encoded(job)
                    with self.assertLogs(main.app.logger, level="WARNING") as logs:
                        response = self.signed_post(value)
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(len(logs.records), 1)
                    self.assertEqual(json.loads(logs.records[0].getMessage()), {
                        "error": code,
                        "contract_version": "dispatch_gateway_robots_policy_diag_v1",
                        "source_sha": main.GATEWAY_SOURCE_SHA,
                    })
                    self.assertEqual(response.get_json(), {
                        "success": False, "error": code,
                        "contract_version": "dispatch_gateway_robots_policy_diag_v1",
                        "source_sha": main.GATEWAY_SOURCE_SHA,
                    })
            auth.assert_not_called()
            enqueue.assert_not_called()

    def test_signature_rejection_precedes_policy_diagnostics(self):
        with patch.object(main.google.auth, "default") as auth, patch.object(main.requests, "post") as enqueue:
            response = self.signed_post(task(respect_robots_txt=False, owner_override=False), valid_signature=False)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.get_json()["error"], "invalid_signature")
            auth.assert_not_called()
            enqueue.assert_not_called()

    def test_both_valid_pairs_forward_the_exact_task_and_keep_dedup(self):
        credentials = Mock(valid=True, token="unit-test-token")
        for respect, override in ((True, False), (False, True)):
            for upstream_status in (200, 409):
                with self.subTest(respect=respect, override=override, upstream_status=upstream_status):
                    value = task(respect_robots_txt=respect, owner_override=override)
                    upstream = Mock(status_code=upstream_status, ok=True)
                    upstream.json.return_value = {"name": value["name"]}
                    with patch.object(main.google.auth, "default", return_value=(credentials, None)), patch.object(main.requests, "post", return_value=upstream) as enqueue:
                        response = self.signed_post(value)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.get_json(), {
                            "success": True, "deduplicated": upstream_status == 409, "taskName": value["name"],
                        })
                        enqueue.assert_called_once()
                        self.assertEqual(enqueue.call_args.kwargs["json"], {"task": value})

    def test_health_reports_configured_source_and_contract(self):
        self.assertEqual(main.GATEWAY_SOURCE_SHA, os.environ.get("FIXLIST_GATEWAY_SOURCE_SHA", "unknown"))
        payload = main.app.test_client().get("/health").get_json()
        self.assertEqual(payload["source_sha"], main.GATEWAY_SOURCE_SHA)
        self.assertEqual(payload["contract_version"], "dispatch_gateway_robots_policy_diag_v1")

    def test_health_reports_the_executing_revision(self):
        # Two revisions built from one commit report the same source_sha, so
        # source_sha cannot say which revision answered. K_REVISION can, and it
        # is the only field a deployment can use to prove the response came
        # from the revision it just promoted rather than the one being drained.
        payload = main.app.test_client().get("/health").get_json()
        self.assertIn("revision", payload)
        self.assertEqual(payload["revision"], main.GATEWAY_RUNTIME_REVISION)

    def test_health_revision_comes_from_the_container_not_the_caller(self):
        # A request must never be able to influence the reported revision.
        client = main.app.test_client()
        payload = client.get(
            "/health",
            query_string={"revision": "attacker-supplied"},
            headers={"K-Revision": "attacker-supplied", "X-Revision": "attacker-supplied"},
        ).get_json()
        self.assertEqual(payload["revision"], main.GATEWAY_RUNTIME_REVISION)
        self.assertNotEqual(payload["revision"], "attacker-supplied")


class ComparisonEndpointTests(unittest.TestCase):
    NOW = 1_790_000_000

    def setUp(self):
        self.clock = patch.object(main.time, "time", return_value=self.NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client = main.app.test_client()

    def document(self):
        from app.authority_seal import create_authority_seal
        from app.repair_identity import REPAIR_IDENTITY_VERSION, build_repair_identity

        def snapshot(scan_id, day, score, pages):
            fix = {
                "fix_id": f"finding-{scan_id}", "rule": "missing_h1", "category": "heading",
                "page_scope": "page", "page_url": "https://example.com/page",
                "affected_pages": ["https://example.com/page"], "repair_surface": "page:/page",
                "remediation_family": "add_semantic_h1", "rule_definition_version": "heading-v1",
                "comparison_profile_version": "standard150-v1", "verification_state": "confirmed",
                "raw_finding": {"published_evidence": {
                    "evidence_url_identity_version": "evidence_url_identity_v2_published_route"}},
            }
            identity = build_repair_identity(fix)
            fix.update(repair_identity_version=REPAIR_IDENTITY_VERSION,
                       repair_identity_state=identity["state"], repair_identity_stable=identity["stable"],
                       repair_fingerprint=identity["fingerprint"])
            date = f"2026-09-{day}T10:00:00Z"
            return {
                "version": "standard_review_snapshot_hmac_identity_v1", "sealed_at": date,
                "owner_user_id": "owner", "scan_id": scan_id, "project_id": "project",
                "normalized_domain": "example.com", "release_fingerprint": "test-release",
                "scan": {"status": "complete", "release_gate_eligible": True,
                         "score_is_provisional": False, "evidence_quality_blocking": False,
                         "website_url": "https://example.com/", "normalized_domain": "example.com",
                         "requested_origin": "https://example.com", "scope_type": "",
                         "requested_path_prefix": "", "completed_at": date,
                         "health_score": score, "pages_crawled": pages},
                "fix_list": {"is_authoritative": True, "score_is_provisional": False,
                             "total_fixes": 1, "health_score": score},
                "recommendations": [fix],
            }
        result = {
            "version": main.COMPARISON_REQUEST_VERSION, "nonce": "ab" * 16,
            "expected_owner_user_id": "owner", "expected_project_id": "project",
            "expected_current_scan_id": "current", "current_previous_scan_id": "previous",
            "previous_snapshot": snapshot("previous", "22", 75, 126),
            "current_snapshot": snapshot("current", "23", 72, 139),
        }
        for side in ("previous", "current"):
            result[f"{side}_proof"] = create_authority_seal(result[f"{side}_snapshot"], main.SIGNING_ROOT)
        return result

    @staticmethod
    def signature(domain, message):
        key = hmac.new(main.SIGNING_ROOT.encode(), domain, hashlib.sha256).digest()
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def post(self, document=None, *, raw=None, timestamp=None, domain=None, mutate=None):
        if raw is None:
            raw = json.dumps(self.document() if document is None else document, ensure_ascii=False).encode()
        timestamp = str(self.NOW) if timestamp is None else timestamp
        signature = self.signature(domain or main.COMPARISON_REQUEST_DOMAIN,
                                   timestamp.encode() + b"\n" + raw)
        if mutate is not None:
            raw = mutate(raw)
        return self.client.post("/compare", data=raw, content_type="application/json", headers={
            "x-fixlist-timestamp": timestamp, "x-fixlist-signature": signature,
        })

    def test_real_comparator_returns_only_signed_presentation_bound_to_exact_pair(self):
        original = self.document()
        before = deepcopy(original)
        with patch.object(main.google.auth, "default") as adc, patch.object(main.requests, "post") as network:
            response = self.post(original)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(original, before)
        adc.assert_not_called()
        network.assert_not_called()
        envelope = response.get_json()
        self.assertEqual(set(envelope), {"payload", "proof"})
        payload = envelope["payload"]
        self.assertEqual(set(payload), {"version", "nonce", "current_scan_id", "previous_scan_id",
                                       "presentation", "source_sha", "generated_at"})
        self.assertEqual(payload["nonce"], original["nonce"])
        self.assertEqual(payload["current_scan_id"], "current")
        self.assertEqual(payload["previous_scan_id"], "previous")
        self.assertEqual(payload["generated_at"], self.NOW)
        self.assertEqual(payload["source_sha"], main.GATEWAY_SOURCE_SHA)
        self.assertEqual(payload["presentation"]["score_line"], "Health score changed from 75 to 72.")
        self.assertFalse(payload["presentation"]["score_direction_claim_allowed"])
        self.assertIn("different numbers of pages", payload["presentation"]["score_caution"])
        expected = self.signature(main.COMPARISON_RESPONSE_DOMAIN, main.stable_serialize(payload).encode())
        self.assertTrue(hmac.compare_digest(envelope["proof"], expected))
        altered = deepcopy(payload)
        altered["current_scan_id"] = "other"
        self.assertNotEqual(envelope["proof"], self.signature(
            main.COMPARISON_RESPONSE_DOMAIN, main.stable_serialize(altered).encode()))
        self.assertNotIn("previous_proof", json.dumps(envelope))
        self.assertNotIn("recommendations", json.dumps(envelope))

    def test_outer_body_tampering_is_rejected_before_comparison(self):
        response = self.post(mutate=lambda raw: raw.replace(b'"owner"', b'"other"', 1))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "invalid_signature")

    def test_signature_domains_are_isolated_from_dispatch_and_response(self):
        for domain in (b"fixlist-dispatch-gateway-v1", main.COMPARISON_RESPONSE_DOMAIN):
            with self.subTest(domain=domain):
                self.assertEqual(self.post(domain=domain).status_code, 401)
        raw = json.dumps({"queue_path": main.QUEUE_PATH, "task": task()}).encode()
        timestamp = str(self.NOW)
        signature = self.signature(main.COMPARISON_REQUEST_DOMAIN, timestamp.encode() + b"\n" + raw)
        response = self.client.post("/dispatch", data=raw, headers={
            "x-fixlist-timestamp": timestamp, "x-fixlist-signature": signature,
        })
        self.assertEqual(response.status_code, 401)

    def test_stale_or_future_replays_fail_freshness(self):
        for skew in (-301, 301):
            with self.subTest(skew=skew):
                response = self.post(timestamp=str(self.NOW + skew))
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json()["error"], "stale_request")

    def test_timestamp_and_nonce_have_canonical_bounded_shapes(self):
        for timestamp in ("", "0", "-1", " 1790000000", "1790000000.0", "0" + str(self.NOW), "1" * 500):
            with self.subTest(timestamp=timestamp):
                self.assertEqual(self.post(timestamp=timestamp).status_code, 401)
        for nonce in (None, 2, "", "a" * 31, "a" * 33, "AB" * 16, "zz" * 16):
            with self.subTest(nonce=nonce):
                document = self.document()
                document["nonce"] = nonce
                self.assertEqual(self.post(document).status_code, 422)

    def test_fresh_duplicate_is_read_only_and_each_response_keeps_its_nonce(self):
        document = self.document()
        self.assertEqual(self.post(document).get_json(), self.post(document).get_json())
        document["nonce"] = "cd" * 16
        self.assertEqual(self.post(document).get_json()["payload"]["nonce"], "cd" * 16)

    def test_signed_outer_envelope_does_not_bypass_snapshot_seals_or_owner_lineage(self):
        mutations = [
            lambda doc: doc["current_snapshot"]["scan"].update(health_score=99),
            lambda doc: doc.update(previous_proof="0" * 64),
            lambda doc: doc.update(expected_owner_user_id="other-owner"),
            lambda doc: doc.update(expected_project_id="other-project"),
            lambda doc: doc.update(expected_current_scan_id="other-current"),
            lambda doc: doc.update(current_previous_scan_id="other-previous"),
            lambda doc: doc.update(signing_key="attacker-key"),
            lambda doc: doc.update(version="unsupported"),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                document = self.document()
                mutation(document)
                response = self.post(document)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.get_json()["error"], "comparison_unavailable")
                self.assertNotIn("snapshot", json.dumps(response.get_json()))

    def test_malformed_deep_duplicate_and_nonfinite_json_fail_closed(self):
        for raw in (b"{", b"[]", b'"text"', b'{"x":1,"x":2}', b'{"x":NaN}',
                    b"[" * 2000 + b"0" + b"]" * 2000, b"\xff"):
            with self.subTest(raw=raw[:30]):
                self.assertEqual(self.post(raw=raw).status_code, 422)

    def test_compare_and_dispatch_enforce_distinct_limits_including_chunked(self):
        for route, limit in (("/compare", main.MAX_COMPARISON_BODY_BYTES),
                             ("/dispatch", main.MAX_DISPATCH_BODY_BYTES)):
            with self.subTest(route=route):
                data = b"x" * (limit + 1)
                self.assertEqual(self.client.post(route, data=data).status_code, 413)
                response = self.client.post(route, environ_overrides={
                    "wsgi.input": io.BytesIO(data), "wsgi.input_terminated": True,
                    "CONTENT_LENGTH": "",
                })
                self.assertEqual(response.status_code, 413)
                self.assertEqual(response.get_json()["error"], "request_too_large")
        self.assertEqual(self.post(raw=b" " * (main.MAX_DISPATCH_BODY_BYTES + 1)).status_code, 422)


class ComparisonPackageTests(unittest.TestCase):
    def test_gateway_pins_the_same_published_url_parser_as_scanner(self):
        repo = Path(__file__).resolve().parents[1]
        def parser_pin(path):
            return next(line for line in path.read_text().splitlines() if line.startswith("ada-url=="))
        self.assertEqual(parser_pin(repo / "dispatch-gateway/requirements.txt"),
                         parser_pin(repo / "scanner-api/requirements.txt"))

    def test_exact_archive_packager_ignores_dirty_sources_and_imports_without_worker(self):
        repo = Path(__file__).resolve().parents[1]
        helper = repo / "scripts/package_dispatch_gateway.sh"
        modules = re.search(r"COMPARISON_MODULES=\((.*?)\)", helper.read_text(), re.S).group(1).split()
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / "source"
            fixture.mkdir()
            files = ["scripts/package_dispatch_gateway.sh"]
            files += [f"dispatch-gateway/{name}" for name in
                      ("main.py", "requirements.txt", "Dockerfile", "test_gateway.py")]
            files += [f"scanner-api/app/{module}" for module in modules]
            for name in files:
                destination = fixture / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / name, destination)

            def run(*args, cwd=fixture):
                clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
                completed = subprocess.run(args, cwd=cwd, env=clean_env, capture_output=True, text=True, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return completed

            run("git", "init", "--quiet")
            run("git", "add", ".")
            run("git", "-c", "user.name=Gateway Package Test", "-c", "user.email=gateway-test@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture archive")
            sha = run("git", "rev-parse", "HEAD").stdout.strip()
            # The helper must package committed bytes even when the working copy
            # later changes. Production additionally requires an exact clean main.
            (fixture / "scanner-api/app/scan_comparison_authority.py").write_text("raise RuntimeError('dirty source')")
            (fixture / "dispatch-gateway/main.py").write_text("dirty gateway source")
            (fixture / "scanner-api/app/untracked.py").write_text("untracked content")
            context = Path(folder) / "context"
            run("bash", str(fixture / "scripts/package_dispatch_gateway.sh"), sha, str(context))
            self.assertEqual((context / ".fixlist-source-sha").read_text().strip(), sha)
            self.assertEqual((context / "main.py").read_bytes(), (repo / "dispatch-gateway/main.py").read_bytes())
            self.assertEqual((context / "Dockerfile").read_bytes(), (repo / "dispatch-gateway/Dockerfile").read_bytes())
            self.assertEqual({p.name for p in (context / "app").iterdir()}, set(modules))
            completed = run(
                sys.executable, "-P", "-c",
                "import sys, unittest; sys.path.insert(0, '.'); import test_gateway; "
                "suite = unittest.defaultTestLoader.loadTestsFromName("
                "'ComparisonEndpointTests.test_real_comparator_returns_only_signed_presentation_bound_to_exact_pair', "
                "test_gateway); result = unittest.TextTestRunner().run(suite); "
                "assert result.wasSuccessful(); assert 'ada_url' in sys.modules; "
                "assert 'app.scan_job' not in sys.modules; assert 'httpx' not in sys.modules",
                cwd=context,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            rejected = subprocess.run([
                "bash", str(fixture / "scripts/package_dispatch_gateway.sh"), sha, str(context),
            ], cwd=fixture, capture_output=True, text=True, check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual((context / ".fixlist-source-sha").read_text().strip(), sha)


if __name__ == "__main__":
    unittest.main()
