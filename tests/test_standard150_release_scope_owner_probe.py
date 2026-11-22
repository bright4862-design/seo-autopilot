"""Hermetic post-deploy verification-scope contract; never contacts Base44.

These tests execute the actual tail of the release launcher after its guarded
deployment step, using mock CLI and verifier binaries. Pre-deploy authorization
and package deployment are intentionally outside this narrow fixture.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/deploy-base44-beta-functions.sh"
POST_DEPLOY = '"$FIXLIST_BASE44_CLI" --app-id "$APP_ID" functions deploy "${CHECKOUT_FUNCTIONS[@]}"'
APP_ID = "6a498732ec779dfaaeab0e53"


class ReleaseScopeOwnerVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fixlist-release-verifier-")
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name)
        content = LAUNCHER.read_text()
        self.assertEqual(content.count(POST_DEPLOY), 1, "Post-deploy boundary changed")
        self.tail = content[content.index(POST_DEPLOY):]
        (self.sandbox / "scripts").mkdir()
        self.trace = self.sandbox / "trace"
        cli = self.sandbox / "mock-cli.sh"
        cli.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'cli:%s\\n' \"$*\" >> \"$TEST_TRACE\"\n"
        )
        cli.chmod(0o755)
        self.cli = cli
        verify = self.sandbox / "scripts/verify-base44-functions.sh"
        verify.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf 'verify:%s:%s\\n' \"${VERIFY_OWNER_DEBUG_RUNTIME:-missing}\" "
            "\"\u0024{BASE44_APP_ID:-missing}\" >> \"$TEST_TRACE\"\n"
            "if [[ \"${SIMULATE_OWNER_STALE:-0}\" == 1 && "
            "\"${VERIFY_OWNER_DEBUG_RUNTIME:-0}\" == 1 ]]; then exit 1; fi\n"
        )
        verify.chmod(0o755)

    def run_scope(self, scope, *, ambient_flag, stale=False):
        setup = "\n".join([
            "set -euo pipefail",
            f"APP_ID={shlex.quote(APP_ID)}",
            f"DEPLOY_SCOPE={shlex.quote(scope)}",
            f"REPO_ROOT={shlex.quote(str(self.sandbox))}",
            f"FIXLIST_BASE44_CLI={shlex.quote(str(self.cli))}",
            "SOURCE_SHA=synthetic-only",
            "FUNCTIONS=(startStandardScanJobV8)",
            "CHECKOUT_FUNCTIONS=(startStandardScanJobV8)",
        ])
        env = dict(os.environ)
        env.update(
            TEST_TRACE=str(self.trace),
            VERIFY_OWNER_DEBUG_RUNTIME=str(ambient_flag),
            BASE44_APP_ID="untrusted-ambient-app",
            SIMULATE_OWNER_STALE="1" if stale else "0",
        )
        result = subprocess.run(
            ["bash", "-c", setup + "\n" + self.tail],
            env=env, capture_output=True, text=True, timeout=10,
        )
        trace = self.trace.read_text().splitlines() if self.trace.exists() else []
        return result, trace

    def test_scanner_only_scope_keeps_six_route_default(self):
        result, trace = self.run_scope("scanner-functions", ambient_flag="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(trace[-1], f"verify:0:{APP_ID}")
        self.assertIn("BASE44_RELEASE_FUNCTIONS_DEPLOYED", result.stdout)

    def test_release_scope_overrides_ambient_and_requires_owner_probe(self):
        result, trace = self.run_scope("release-functions", ambient_flag="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(trace[-1], f"verify:1:{APP_ID}")
        self.assertIn("BASE44_RELEASE_FUNCTIONS_DEPLOYED", result.stdout)

    def test_owner_mismatch_suppresses_release_success_receipt(self):
        result, trace = self.run_scope("release-functions", ambient_flag="0", stale=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(trace[-1], f"verify:1:{APP_ID}")
        self.assertNotIn("BASE44_RELEASE_FUNCTIONS_DEPLOYED", result.stdout)

    def test_scanner_only_does_not_depend_on_owner_package(self):
        result, trace = self.run_scope("scanner-functions", ambient_flag="1", stale=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(trace[-1], f"verify:0:{APP_ID}")


if __name__ == "__main__":
    unittest.main()
