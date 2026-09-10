import assert from "node:assert/strict";
import { chmodSync, cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const script = "scripts/deploy-base44-beta-functions.sh";
const workflow = readFileSync(".github/workflows/fixlist-base44-release-publish.yml", "utf8");
const scannerFunctions = [
  "startStandardScanJobV3",
  "durableScanWorkerControlV3",
  "persistDurableScanAuthorityV3",
  "persistLimitedScanResultV3",
  "getCustomerScanResultV3",
  "deleteCustomerScanDataV3",
];

function fixture({ verifierExit = 0 } = {}) {
  const root = mkdtempSync(join(tmpdir(), "fixlist-functions-only-"));
  mkdirSync(join(root, "scripts", "lib"), { recursive: true });
  mkdirSync(join(root, "bin"));
  cpSync(script, join(root, script));
  writeFileSync(join(root, "scripts", "base44_release_manifest.mjs"), "");
  writeFileSync(join(root, "scripts", "lib", "release-source-guard.sh"), `
fixlist_require_exact_main() { FIXLIST_EXACT_SOURCE_SHA="$2"; }
`);
  writeFileSync(join(root, "scripts", "lib", "base44-pinned-cli.sh"), `
fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_FAKE_CLI"; export FIXLIST_BASE44_CLI; }
fixlist_require_base44_owner() { :; }
fixlist_set_base44_release_source_sha() { printf 'set-release-source\\n' >> "$TEST_MUTATIONS"; }
`);
  writeFileSync(join(root, "scripts", "verify-base44-functions.sh"), `#!/usr/bin/env bash
printf 'verifier-ran\\n' >> "$TEST_MUTATIONS"
exit ${verifierExit}
`);
  const fakeCli = join(root, "bin", "base44");
  writeFileSync(fakeCli, `#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$TEST_CLI_CALLS"
`);
  chmodSync(fakeCli, 0o755);
  chmodSync(join(root, "scripts", "verify-base44-functions.sh"), 0o755);
  const calls = join(root, "cli-calls");
  const mutations = join(root, "mutations");
  const run = (scope) => spawnSync("bash", [join(root, script)], {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${join(root, "bin")}:${process.env.PATH}`,
      SOURCE_SHA: "a".repeat(40),
      CONFIRM: "a".repeat(40),
      BASE44_EXPECTED_OWNER: "owner@example.com",
      DEPLOY_SCOPE: scope,
      TEST_FAKE_CLI: fakeCli,
      TEST_CLI_CALLS: calls,
      TEST_MUTATIONS: mutations,
    },
  });
  return { root, calls, mutations, run };
}

function contents(path) {
  try { return readFileSync(path, "utf8"); } catch { return ""; }
}

test("scanner-functions deploys and attests exactly the six V3 scanner routes", () => {
  const f = fixture();
  try {
    const result = f.run("scanner-functions");
    assert.equal(result.status, 0, result.stderr);
    const deploy = contents(f.calls).split("\n").find((line) => line.includes(" functions deploy "));
    assert.ok(deploy, contents(f.calls));
    for (const name of scannerFunctions) assert.match(deploy, new RegExp(`(?:^| )${name}(?: |$)`));
    assert.equal(deploy.trim().split(/\s+/).slice(-scannerFunctions.length).join(" "), scannerFunctions.join(" "));
    for (const forbidden of ["createAccessCheckout", "stripeWebhook", "ownerScanDebugControl", "site", "entities"])
      assert.doesNotMatch(contents(f.calls), new RegExp(forbidden));
    assert.match(contents(f.mutations), /verifier-ran/);
    assert.match(result.stdout, /BASE44_RELEASE_FUNCTIONS_DEPLOYED/);
    assert.match(result.stdout, /function_count=6/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("verifier failure returns nonzero and suppresses the deployment success marker", () => {
  const f = fixture({ verifierExit: 19 });
  try {
    const result = f.run("scanner-functions");
    assert.equal(result.status, 19);
    assert.match(contents(f.mutations), /verifier-ran/);
    assert.doesNotMatch(result.stdout, /BASE44_RELEASE_FUNCTIONS_DEPLOYED/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("unknown deployment scope fails before any mutation", () => {
  const f = fixture();
  try {
    const result = f.run("scanner-functions-and-site");
    assert.notEqual(result.status, 0);
    assert.equal(contents(f.calls), "");
    assert.equal(contents(f.mutations), "");
    assert.match(result.stderr, /deployment scope/i);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("hosted release dispatch defaults safely and preserves shared release protections", () => {
  assert.match(workflow, /deployment_target:[\s\S]*default:\s*scanner-functions[\s\S]*options:[\s\S]*- scanner-functions[\s\S]*- site-and-functions/);
  assert.match(workflow, /case "\$INPUT_DEPLOYMENT_TARGET" in[\s\S]*scanner-functions\|site-and-functions[\s\S]*Refusing/);
  assert.match(workflow, /if:.*deployment_target.*scanner-functions[\s\S]*DEPLOY_SCOPE:\s*scanner-functions[\s\S]*deploy-base44-beta-functions\.sh/);
  assert.match(workflow, /if:.*deployment_target.*site-and-functions[\s\S]*deploy-base44-beta-site\.sh/);
  assert.match(workflow, /group:\s*fixlist-base44-hosted-controls-v2/);
  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /git rev-parse origin\/main/);
  assert.match(workflow, /BASE44_EXPECTED_OWNER: \$\{\{ secrets\.BASE44_EXPECTED_OWNER \}\}/);
  assert.match(workflow, /if: \$\{\{ always\(\) \}\}[\s\S]*rm -rf "\$HOME\/\.base44"/);
});
