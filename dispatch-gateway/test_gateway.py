import base64
import importlib.util
import json
import os
import sys
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
