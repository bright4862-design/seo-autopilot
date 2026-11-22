"""Offline read-only package-identity probe tests; never invoke Base44."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = 'scripts/verify-base44-functions.sh'
RESOLVER = 'scripts/lib/base44-public-routes.mjs'
ROUTES = 'data/base44-function-routes.json'
GENERATED = 'data/generated-staged-v9-routes.json'
SCANNER = (
    'startStandardScanJobV8', 'durableScanWorkerControlV8',
    'persistDurableScanAuthorityV8', 'persistLimitedScanResultV8',
    'getCustomerScanResultV8', 'deleteCustomerScanDataV8',
)
OWNER = 'ownerScanDebugControl'


class OwnerRuntimeProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fixlist-owner-probe-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (VERIFIER, RESOLVER, ROUTES, GENERATED):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        generator = self.root / 'scripts/generate_release_contracts.mjs'
        generator.write_text("""
const [mode, name] = process.argv.slice(2);
if (mode === '--build-id') process.stdout.write('a'.repeat(64));
else if (mode === '--activation-id') process.stdout.write(name + '-test');
else if (mode !== '--check') process.exitCode = 2;
""")
        curl = self.root / 'bin/curl'
        curl.parent.mkdir()
        curl.write_text("""#!/usr/bin/env bash
set -euo pipefail
body=''; url=''
while (( $# )); do
  if [[ "$1" == '-o' ]]; then body="$2"; shift 2; else url="$1"; shift; fi
done
name="\${url##*/}"
printf '%s\\n' "$name" >> "$TEST_CALLS"
build='""" + 'a' * 64 + """'
if [[ "$name" == "\${TEST_STALE:-}" ]]; then build='""" + 'b' * 64 + """'; fi
printf '{"build_id":"%s","runtime_activation_id":"%s-test"}\\n' "$build" "$name" > "$body"
printf 405
""")
        curl.chmod(0o755)
        self.calls = self.root / 'calls.txt'

    def run_probe(self, **extra):
        env = dict(os.environ)
        env.update({
            'PATH': str(self.root / 'bin') + os.pathsep + env.get('PATH', ''),
            'BASE44_APP_ID': '6a498732ec779dfaaeab0e53',
            'BASE44_FUNCTION_ORIGIN': 'https://base44.app',
            'TEST_CALLS': str(self.calls),
            'VERIFY_OWNER_DEBUG_RUNTIME': '0',
            'PROBE_ATTEMPTS': '1',
            'PROBE_DELAY_SECONDS': '0',
        })
        env.update(extra)
        return subprocess.run(['bash', str(self.root / VERIFIER)], cwd=self.root,
                              env=env, capture_output=True, text=True, timeout=20)

    def names(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_default_remains_six_scanner_routes(self):
        result = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.names(), list(SCANNER))
        self.assertIn('BASE44_FUNCTIONS_SOURCE_VERIFIED', result.stdout)

    def test_owner_opt_in_checks_exact_seventh_build(self):
        result = self.run_probe(VERIFY_OWNER_DEBUG_RUNTIME='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.names(), [*SCANNER, OWNER])
        self.assertIn('FUNCTION_RUNTIME_VERIFIED name=ownerScanDebugControl', result.stdout)

    def test_stale_owner_package_fails_even_when_scanner_routes_match(self):
        result = self.run_probe(VERIFY_OWNER_DEBUG_RUNTIME='1', TEST_STALE=OWNER)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.names(), [*SCANNER, OWNER])
        self.assertIn('FUNCTION_BUILD_MISMATCH name=ownerScanDebugControl', result.stderr)
        self.assertNotIn('BASE44_FUNCTIONS_SOURCE_VERIFIED', result.stdout)

    def test_invalid_flag_and_wrong_target_fail_before_network(self):
        for change in (
            {'VERIFY_OWNER_DEBUG_RUNTIME': 'yes'},
            {'VERIFY_OWNER_DEBUG_RUNTIME': '1', 'BASE44_FUNCTION_ORIGIN': 'https://other.invalid'},
            {'VERIFY_OWNER_DEBUG_RUNTIME': '1', 'BASE44_APP_ID': 'other-app'},
        ):
            with self.subTest(change=change):
                result = self.run_probe(**change)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self.names(), [])


if __name__ == '__main__':
    unittest.main()
