"""Synthetic-only Cloud Run v1 control-plane fixtures; never contacts GCP."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/verify_standard150_serving_revision.py"
spec = importlib.util.spec_from_file_location("serving_guard", MODULE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

SERVICE = "fixlist-standard150-worker"
REVISION = "fixlist-standard150-worker-00104-l79"


def service():
    return {"metadata": {"name": SERVICE, "generation": 9}, "status": {
        "observedGeneration": 9, "conditions": [{"type": "Ready", "status": "True"}],
        "url": "https://worker-example.run.app", "traffic": [
            {"revisionName": REVISION, "percent": 100},
            {"revisionName": "fixlist-standard150-worker-00105-abc", "percent": 0, "tag": "candidate"}],
    }}


def revision():
    return {"metadata": {"name": REVISION, "generation": 1,
                         "labels": {"serving.knative.dev/service": SERVICE}},
            "status": {"observedGeneration": 1, "conditions": [{"type": "Ready", "status": "True"}]}}


class ServingProofTest(unittest.TestCase):
    def test_good_current_ready_revision(self):
        self.assertEqual(guard.select_serving_revision(service()), REVISION)
        guard.verify_revision_ready(revision(), REVISION, SERVICE)

    def test_fail_closed_service_cases(self):
        for mutation in [
            lambda s: s["status"]["conditions"].__setitem__(0, {"type": "Ready", "status": "False"}),
            lambda s: s["status"].__setitem__("observedGeneration", 8),
            lambda s: s["status"]["traffic"].append({"revisionName": "different", "percent": 100}),
            lambda s: s["status"]["traffic"][0].__setitem__("tag", "serving"),
            lambda s: s["status"]["traffic"][0].__setitem__("revisionName", ""),
        ]:
            with self.subTest(mutation=mutation):
                s = service()
                mutation(s)
                with self.assertRaises(guard.ServingRevisionError):
                    guard.select_serving_revision(s)

    def test_fail_closed_selected_revision_cases(self):
        for key, value in [("name", "other"), ("generation", 2)]:
            r = revision()
            r["metadata"][key] = value
            with self.subTest(key=key), self.assertRaises(guard.ServingRevisionError):
                guard.verify_revision_ready(r, REVISION, SERVICE)
        for field, value in [("status", "False"), ("owner", "other")]:
            r = revision()
            if field == "status":
                r["status"]["conditions"][0]["status"] = value
            else:
                r["metadata"]["labels"]["serving.knative.dev/service"] = value
            with self.subTest(field=field), self.assertRaises(guard.ServingRevisionError):
                guard.verify_revision_ready(r, REVISION, SERVICE)

    def test_cli_read_only_two_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Path(tmp) / "service.json"
            r = Path(tmp) / "revision.json"
            s.write_text(json.dumps(service()))
            r.write_text(json.dumps(revision()))
            command = [sys.executable, str(MODULE), "--service-json", str(s)]
            first = subprocess.run(command, check=True, text=True, capture_output=True)
            self.assertEqual(first.stdout.strip(), REVISION)
            checked = subprocess.run([*command, "--revision-json", str(r)], check=True, text=True, capture_output=True)
            self.assertEqual(checked.stdout.strip(), REVISION)
            changed = service()
            changed["status"]["observedGeneration"] = 8
            s.write_text(json.dumps(changed))
            rejected = subprocess.run([*command, "--revision-json", str(r)], text=True, capture_output=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("unreconciled", rejected.stderr)
