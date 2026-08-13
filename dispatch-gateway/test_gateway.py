import base64
import importlib
import json
import os
import time
import unittest

os.environ.setdefault(
    "SCAN_TASKS_QUEUE_PATH",
    "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150",
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

main = importlib.import_module("main")


def encoded(value):
    return base64.b64encode(json.dumps(value).encode("utf-8")).decode("ascii")


def task(*, scan_id="scan_abc123", drain=False, attempt=1):
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
            "respect_robots_txt": True,
        })

    value = {
        "name": f"{main.QUEUE_PATH}/tasks/{short_name}",
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
        return main.validate_dispatch({
            "queue_path": queue_path or main.QUEUE_PATH,
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

    def test_exact_drain_task_is_accepted(self):
        accepted, error = self.validate(task(drain=True))
        self.assertIsNone(error)
        self.assertIsNotNone(accepted)

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

    def test_robots_policy_is_pinned(self):
        value = task()
        job = json.loads(base64.b64decode(value["httpRequest"]["body"]))
        job["respect_robots_txt"] = False
        value["httpRequest"]["body"] = encoded(job)
        self.assertRejected(value, "invalid_robots_policy")

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


if __name__ == "__main__":
    unittest.main()
