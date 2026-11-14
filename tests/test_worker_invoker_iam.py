"""Regression for the Cloud Run v1 invoker-IAM bypass release boundary."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_worker_invoker_iam.py"
POST_DEPLOY = ROOT / "scripts" / "post_deploy_verify.sh"


def run_metadata(service):
    payload = service if isinstance(service, str) else json.dumps(service)
    return subprocess.run([sys.executable, str(SCRIPT)], input=payload,
                          capture_output=True, text=True, check=False)


class WorkerInvokerIamBoundaryTest(unittest.TestCase):
    def test_default_enforcement_without_annotation(self):
        self.assertEqual(run_metadata({"metadata": {"annotations": {}}}).returncode, 0)

    def test_explicit_enforcement(self):
        self.assertEqual(run_metadata({"metadata": {"annotations": {
            "run.googleapis.com/invoker-iam-disabled": "false"
        }}}).returncode, 0)

    def test_public_bypass_even_when_private_iam_policy_could_look_clean(self):
        result = run_metadata({"metadata": {"annotations": {
            "run.googleapis.com/invoker-iam-disabled": "true"
        }}})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_ambiguous_or_malformed_values_fail_closed(self):
        for value in ("TRUE", "", "False", None, True, 0, "0"):
            with self.subTest(value=value):
                self.assertEqual(run_metadata({"metadata": {"annotations": {
                    "run.googleapis.com/invoker-iam-disabled": value
                }}}).returncode, 1)

    def test_unreadable_or_malformed_service_fails_closed(self):
        for service in ("", "{", "null", "[]", "{}", '{"metadata":[]}',
                        '{"metadata":{"annotations":null}}'):
            with self.subTest(payload=service):
                self.assertEqual(run_metadata(service).returncode, 1)

    def test_duplicate_service_annotation_cannot_hide_public_flag(self):
        payload = ('{"metadata":{"annotations":{'
                   '"run.googleapis.com/invoker-iam-disabled":"true",'
                   '"run.googleapis.com/invoker-iam-disabled":"false"}}}')
        self.assertEqual(run_metadata(payload).returncode, 1)

    def test_duplicate_metadata_member_cannot_hide_public_flag(self):
        payload = ('{"metadata":{"annotations":{'
                   '"run.googleapis.com/invoker-iam-disabled":"true"}},'
                   '"metadata":{"annotations":{'
                   '"run.googleapis.com/invoker-iam-disabled":"false"}}}')
        self.assertEqual(run_metadata(payload).returncode, 1)

    def test_post_deploy_privacy_gate_executes_the_guard(self):
        source = POST_DEPLOY.read_text(encoding="utf-8")
        self.assertIn("scripts/verify_worker_invoker_iam.py", source)
        self.assertIn('fail "Cloud Run invoker IAM check is disabled or metadata is ambiguous"', source)


if __name__ == "__main__":
    unittest.main()
