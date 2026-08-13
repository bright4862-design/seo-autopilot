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
os.environ.setdefault("SCAN_EVIDENCE_SIGNING_KEY", "unit-test-root-secret")

main = importlib.import_module("main")


def encoded(value):
    return base64.b64encode(json.dumps(value).encode()).decode()


def task(*, scan_id="scan123", drain=False):
    suffix = f"standard150-{'drain-' if drain else ''}{scan_id}-a1"
    target = main.DRAIN_URL if drain else main.WORKER_URL
    body = {
        "scan_id": scan_id,
        "request_id": "req123",
    }
    if drain:
        body["drain_after"] = "2099-01-01T00:00:00Z"
    else:
        body.update({"scan_mode": "standard_150", "respect_robots_txt": True})
    value = {
        "name": f"{main.QUEUE_PATH}/tasks/{suffix}",
        "dispatchDeadline": "480s",
        "httpRequest": {
            "url": target,
            "httpMethod": "POST",
            "headers": {"content-type": "application/json"},
            "body": encoded(body),
            "oidcToken": {
                "serviceAccountEmail": main.INVOKER_SA,
                "audience": main.WORKER_ORIGIN,
            },
        },
    }
    if drain:
        value["scheduleTime"] = "2099-01-01T00:00:00Z"
    return value


class GatewayContractTests(unittest.TestCase):
    def validate(self, value):
        return main.validate_dispatch({"queue_path": main.QUEUE_PATH, "task": value})

    def test_accepts_exact_scan_task(self):
        accepted, error = self.validate(task())
        self.assertIsNone(error)
        self.assertIsNotNone(accepted)

    def test_accepts_exact_drain_task(self):
        accepted, error = self.validate(task(drain=True))
        self.assertIsNone(error)
        self.assertIsNotNone(accepted)

    def test_rejects_arbitrary_target(self):
        value = task()
        value["httpRequest"]["url"] = "https://example.com/"
        _, error = self.validate(value)
        self.assertEqual(error, "invalid_worker_target")

    def test_rejects_wrong_invoker(self):
        value = task()
        value["httpRequest"]["oidcToken"]["serviceAccountEmail"] = "other@example.com"
        _, error = self.validate(value)
        self.assertEqual(error, "invalid_invoker")

    def test_rejects_wrong_mode(self):
        value = task()
        body = json.loads(base64.b64decode(value["httpRequest"]["body"]))
        body["scan_mode"] = "premium_5000"
        value["httpRequest"]["body"] = encoded(body)
        _, error = self.validate(value)
        self.assertEqual(error, "invalid_scan_mode")

    def test_rejects_scan_id_mismatch(self):
        value = task(scan_id="scan123")
        body = json.loads(base64.b64decode(value["httpRequest"]["body"]))
        body["scan_id"] = "scan999"
        value["httpRequest"]["body"] = encoded(body)
        _, error = self.validate(value)
        self.assertEqual(error, "scan_identity_mismatch")

    def test_rejects_missing_drain_schedule(self):
        value = task(drain=True)
        del value["scheduleTime"]
        _, error = self.validate(value)
        self.assertEqual(error, "missing_drain_schedule")

    def test_timestamped_signature_round_trip(self):
        timestamp = str(int(time.time()))
        raw = b'{"queue_path":"x","task":null}'
        signature = main._expected_signature(timestamp, raw)
        self.assertEqual(len(signature), 64)
        self.assertNotEqual(signature, main._expected_signature(str(int(timestamp) + 1), raw))


if __name__ == "__main__":
    unittest.main()
