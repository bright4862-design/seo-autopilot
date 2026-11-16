"""Synthetic, read-only build attribution regression cases."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from scripts.resolve_worker_build_provenance import ProvenanceError, release_sha_for_revision

SOURCE_A = "a" * 40
SOURCE_B = "b" * 40
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64
REPO = "europe-west1-docker.pkg.dev/acme/worker/standard150"


def revision(spec_image=f"{REPO}:release-b", resolved=f"{REPO}@{DIGEST_B}"):
    return {"spec": {"containers": [{"image": spec_image}]}, "status": {"imageDigest": resolved}}


def build(build_id, source_sha, digest, *, repo=REPO, status="SUCCESS"):
    return {
        "id": build_id, "status": status,
        "results": {"images": [{"name": repo + ":build-tag", "digest": digest}]},
        "substitutions": {"_RELEASE_SHA": source_sha},
    }


class TestWorkerBuildProvenance(unittest.TestCase):
    def setUp(self):
        self.a = build("newer-A", SOURCE_A, DIGEST_A)
        self.b = build("older-B", SOURCE_B, DIGEST_B)

    def assert_reject(self, reason, rev, builds):
        with self.assertRaisesRegex(ProvenanceError, reason):
            release_sha_for_revision(rev, builds)

    def test_tagged_revision_ignores_newer_build_of_same_repository(self):
        self.assertEqual(release_sha_for_revision(revision(), [self.a, self.b]), (SOURCE_B, "older-B"))
        self.assertEqual(release_sha_for_revision(revision(), [self.b, self.a]), (SOURCE_B, "older-B"))

    def test_digest_pinned_revision_works(self):
        rev = revision(spec_image=f"{REPO}@{DIGEST_B}")
        self.assertEqual(release_sha_for_revision(rev, [self.a, self.b])[0], SOURCE_B)

    def test_refuse_missing_or_malformed_resolved_digest(self):
        for resolved in ["", "sha256:abc", "not-a-digest"]:
            self.assert_reject("revision_resolved_digest", revision(resolved=resolved), [self.b])

    def test_refuse_spec_and_status_disagreement(self):
        self.assert_reject("revision_spec_status_digest_mismatch", revision(spec_image=f"{REPO}@{DIGEST_A}"), [self.b])

    def test_refuse_foreign_repository_even_same_digest(self):
        self.assert_reject("resolved_digest_build_not_found", revision(), [
            build("foreign", SOURCE_B, DIGEST_B, repo="us.gcr.io/other/standard150")])

    def test_refuse_ambiguous_builds_even_with_same_sha(self):
        self.assert_reject("resolved_digest_multiple_builds", revision(), [
            self.b, build("copy", SOURCE_B, DIGEST_B)])

    def test_refuse_failed_build_and_invalid_sha(self):
        self.assert_reject("resolved_digest_build_not_successful", revision(), [
            build("fail", SOURCE_B, DIGEST_B, status="FAILURE")])
        self.assert_reject("release_sha_missing_or_invalid", revision(), [
            build("bad", "head", DIGEST_B)])

    def test_cli_fails_closed_and_emits_only_source_sha_on_stdout(self):
        helper = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "resolve_worker_build_provenance.py"
        with tempfile.TemporaryDirectory() as temp:
            revfile = pathlib.Path(temp) / "revision.json"
            revfile.write_text(json.dumps(revision()), encoding="utf-8")
            command = [sys.executable, str(helper), "--revision-json", str(revfile)]
            ok = subprocess.run(command, input=json.dumps([self.a, self.b]), text=True, capture_output=True)
            self.assertEqual(ok.returncode, 0)
            self.assertEqual(ok.stdout.strip(), SOURCE_B)
            missing = subprocess.run(command, input=json.dumps([self.a]), text=True, capture_output=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertEqual(missing.stdout.strip(), "")
            self.assertIn("INDETERMINATE", missing.stderr)


if __name__ == "__main__":
    unittest.main()
