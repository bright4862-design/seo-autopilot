import assert from 'node:assert/strict';
import {chmodSync, cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import test from 'node:test';

const names = [
  'startStandardScanJobV9', 'durableScanWorkerControlV9',
  'persistDurableScanAuthorityV9', 'persistLimitedScanResultV9',
  'getCustomerScanResultV9', 'deleteCustomerScanDataV9',
];
const sourceSha = 'a'.repeat(40);
const appId = '6a498732ec779dfaaeab0e53';
const script = 'scripts/verify-base44-v9-stored-packages.sh';
const contents = file => existsSync(file) ? readFileSync(file, 'utf8') : '';

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'fixlist-v9-readonly-'));
  mkdirSync(join(root, 'scripts/lib'), {recursive:true});
  mkdirSync(join(root, 'base44/functions'), {recursive:true});
  mkdirSync(join(root, 'bin'), {recursive:true});
  cpSync(script, join(root, script));
  cpSync('scripts/base44_release_manifest.mjs', join(root, 'scripts/base44_release_manifest.mjs'));
  writeFileSync(join(root, 'scripts/generate_release_contracts.mjs'),
    "if (process.argv[2] !== '--check') process.exit(1);\n");
  writeFileSync(join(root, 'scripts/lib/release-source-guard.sh'),
    'fixlist_require_exact_main() { [[ "$TEST_GUARD_FAIL" != yes ]]; }\n');
  writeFileSync(join(root, 'scripts/lib/base44-pinned-cli.sh'),
    'fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_FAKE_CLI"; export FIXLIST_BASE44_CLI; }\n' +
    'fixlist_require_base44_owner() { [[ "$TEST_OWNER_FAIL" != yes ]]; }\n');

  for (const name of names) {
    const dir = join(root, 'base44/functions', name);
    mkdirSync(dir, {recursive:true});
    writeFileSync(join(dir, 'function.jsonc'), JSON.stringify({name, entry:'entry.ts'}));
    writeFileSync(join(dir, 'entry.ts'), 'export default function handler() { return 1; }\n');
  }

  const calls = join(root, 'calls');
  const fake = join(root, 'bin/base44');
  writeFileSync(fake, [
    '#!/usr/bin/env bash',
    'set -euo pipefail',
    'echo "$*" >> "$TEST_CLI_CALLS"',
    '[[ "$1" == --app-id && "$2" == ' + appId + ' && "$3" == functions && "$4" == pull ]] || exit 9',
    'name="$5"',
    '[[ "$name" != "$TEST_FAIL_PULL" ]] || exit 12',
    '[[ "$name" != "$TEST_OMIT_PULL" ]] || exit 0',
    'mkdir -p base44/functions',
    'cp -R "$TEST_PACKAGES_ROOT/$name" "base44/functions/$name"',
    'if [[ "$name" == "$TEST_TAMPER_PULL" ]]; then echo "// altered" >> "base44/functions/$name/entry.ts"; fi',
  ].join('\n') + '\n');
  chmodSync(fake, 0o755);

  function run(extra = {}) {
    return spawnSync('bash', [join(root, script)], {
      cwd:root, encoding:'utf8',
      env:{
        ...process.env, SOURCE_SHA:sourceSha, BASE44_APP_ID:appId,
        BASE44_EXPECTED_OWNER:'test-owner',
        TEST_FAKE_CLI:fake, TEST_CLI_CALLS:calls,
        TEST_PACKAGES_ROOT:join(root, 'base44/functions'),
        TEST_GUARD_FAIL:'', TEST_OWNER_FAIL:'', TEST_FAIL_PULL:'',
        TEST_OMIT_PULL:'', TEST_TAMPER_PULL:'', ...extra,
      },
    });
  }
  return {root, calls, run, cleanup() { rmSync(root, {recursive:true, force:true}); }};
}

test('fresh V9 per-function package pull verifies all six without any mutation', () => {
  const f = fixture();
  try {
    const response = f.run();
    assert.equal(response.status, 0, response.stderr);
    assert.match(response.stdout, /BASE44_V9_STORED_PACKAGES_MATCHED/);
    assert.match(response.stdout, /runtime_identity=UNVERIFIED published_route=UNVERIFIED/);
    const calls = contents(f.calls).trim().split('\n');
    assert.deepEqual(calls, names.map(name => '--app-id ' + appId + ' functions pull ' + name));
    assert.doesNotMatch(contents(f.calls), /functions (deploy|delete)|secrets|site deploy|entities push|--force/i);
  } finally { f.cleanup(); }
});

for (const [name, extra] of Object.entries({
  wrong_app: {BASE44_APP_ID:'foreign'},
  missing_source_sha: {SOURCE_SHA:''},
  source_not_main: {TEST_GUARD_FAIL:'yes'},
  owner_unverified: {TEST_OWNER_FAIL:'yes'},
})) {
  test('preflight rejects ' + name + ' before any CLI pull', () => {
    const f = fixture();
    try {
      const result = f.run(extra);
      assert.notEqual(result.status, 0);
      assert.equal(contents(f.calls), '');
      assert.doesNotMatch(result.stdout, /BASE44_V9_STORED_PACKAGES_MATCHED/);
    } finally { f.cleanup(); }
  });
}

for (const [name, extra] of Object.entries({
  failed_pull: {TEST_FAIL_PULL:names[0]},
  false_success_missing_pull: {TEST_OMIT_PULL:names[0]},
  pulled_byte_drift: {TEST_TAMPER_PULL:names[2]},
})) {
  test('backend package readback fails closed on ' + name, () => {
    const f = fixture();
    try {
      const result = f.run(extra);
      assert.notEqual(result.status, 0);
      assert.doesNotMatch(result.stdout, /BASE44_V9_STORED_PACKAGES_MATCHED/);
      assert.doesNotMatch(contents(f.calls), /functions deploy|secrets|site deploy|entities push/);
    } finally { f.cleanup(); }
  });
}

test('the operator script cannot activate a customer release', () => {
  const source = readFileSync(script, 'utf8');
  assert.match(source, /fixlist_require_exact_main/);
  assert.match(source, /fixlist_require_base44_owner/);
  assert.match(source, /functions pull "\$name"/);
  assert.doesNotMatch(source, /functions deploy|secrets set|site deploy|entities push|workflow_dispatch|scan-job|createTask|--force/);
});
