"""Offline regression tests for #378 signing-reference diagnostic (no credentials)."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("signref", ROOT / "scripts/read_only_signing_ref.py")
signref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signref)


def fixtures():
    service = {"metadata": {"name": "fixlist-standard150-worker"},
               "status": {"traffic": [{"revisionName": "serving-a", "percent": 100},
                                      {"revisionName": "candidate-b", "percent": 0, "tag": "candidate"}]}}
    revision = {"metadata": {"name": "serving-a"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                "spec": {"containers": [{"env": [{"name": "SCAN_EVIDENCE_SIGNING_KEY",
                                                 "valueFrom": {"secretKeyRef": {"name": "SCAN_EVIDENCE_SIGNING_KEY", "key": "7"}}}]}]}}
    return service, revision


class SigningMetadataTest(unittest.TestCase):
    def test_positive_is_metadata_only(self):
        service, rev = fixtures()
        self.assertEqual(signref.check(service, rev, "fixlist-standard150-worker"),
                         ("serving-a", "SCAN_EVIDENCE_SIGNING_KEY", "7"))

    def test_reject_plaintext_even_with_reference(self):
        service, rev = fixtures()
        rev["spec"]["containers"][0]["env"][0]["value"] = "SECRET_BYTES"
        with self.assertRaisesRegex(signref.Unknown, "plaintext"):
            signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_unpinned_secret_versions(self):
        for version in ("latest", "0", "07", "", 7):
            with self.subTest(version=version):
                service, rev = fixtures()
                rev["spec"]["containers"][0]["env"][0]["valueFrom"]["secretKeyRef"]["key"] = version
                with self.assertRaisesRegex(signref.Unknown, "unversioned"):
                    signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_duplicate_signing_binding(self):
        service, rev = fixtures()
        rev["spec"]["containers"][0]["env"].append(rev["spec"]["containers"][0]["env"][0].copy())
        with self.assertRaisesRegex(signref.Unknown, "duplicate"):
            signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_candidate_as_serving_revision(self):
        service, rev = fixtures()
        rev["metadata"]["name"] = "candidate-b"
        with self.assertRaisesRegex(signref.Unknown, "mismatched"):
            signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_not_ready_revision(self):
        service, rev = fixtures()
        rev["status"]["conditions"][0]["status"] = "False"
        with self.assertRaisesRegex(signref.Unknown, "not_ready"):
            signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_split_traffic(self):
        service, rev = fixtures()
        service["status"]["traffic"] = [{"revisionName": "a", "percent": 50}, {"revisionName": "b", "percent": 50}]
        with self.assertRaisesRegex(signref.Unknown, "ambiguous"):
            signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_boolean_percent(self):
        service, rev = fixtures()
        service["status"]["traffic"][0]["percent"] = True
        with self.assertRaisesRegex(signref.Unknown, "malformed"):
            signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_foreign_service(self):
        service, rev = fixtures()
        service["metadata"]["name"] = "foreign-worker"
        with self.assertRaisesRegex(signref.Unknown, "wrong_worker"):
            signref.check(service, rev, "fixlist-standard150-worker")

    def test_reject_multiple_containers(self):
        service, rev = fixtures()
        rev["spec"]["containers"].append({"env": []})
        with self.assertRaisesRegex(signref.Unknown, "containers"):
            signref.check(service, rev, "fixlist-standard150-worker")


if __name__ == "__main__":
    unittest.main()
