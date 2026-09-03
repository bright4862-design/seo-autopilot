import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import test from "node:test";

const SCRIPT = "scripts/recover-base44-stale-release-functions.sh";
const WORKFLOW = ".github/workflows/fixlist-base44-stale-function-recovery.yml";
const recovery = fs.readFileSync(SCRIPT, "utf8");
const workflow = fs.readFileSync(WORKFLOW, "utf8");

function classify(status, body, buildId, expected) {
  const out = execFileSync(
    "bash",
    [
      "-c",
      [
        'FIXLIST_STALE_RECOVERY_LIB_ONLY=1 source "$0"',
        'PROBE_STATUS="$1"',
        'PROBE_BODY="$2"',
        'PROBE_BUILD_ID="$3"',
        'if route_reaches_json_handler && route_serves_expected_build "$4"; then echo exact',
        'elif route_reaches_json_handler; then echo stale',
        'else echo refuse',
        'fi',
      ].join("; "),
      SCRIPT,
      String(status),
      body,
      buildId,
      expected,
    ],
    { encoding: "utf8" },
  );
  return out.trim();
}

test("stale recovery covers exactly the nine published release functions", () => {
  const list = recovery.match(/RECOVERY_FUNCTIONS=\(([^)]*)\)/s)[1]
    .split("\n").map((line) => line.trim()).filter(Boolean);
  assert.deepEqual(list, [
    "ownerScanDebugControl",
    "durableScanWorkerControl",
    "persistDurableScanAuthority",
    "persistLimitedScanResult",
    "deleteCustomerScanData",
    "getCustomerScanResult",
    "startStandardScanJob",
    "createAccessCheckout",
    "stripeWebhook",
  ]);
});

test("only an exact build match skips recreation", () => {
  const expected = "a".repeat(64);
  assert.equal(
    classify(405, '{"success":false,"build_id":"' + expected + '"}', expected, expected),
    "exact",
  );
  assert.equal(
    classify(405, '{"success":false,"error":"Method not allowed"}', "", expected),
    "stale",
  );
  assert.equal(
    classify(405, '{"success":false,"build_id":"' + "b".repeat(64) + '"}', "b".repeat(64), expected),
    "stale",
  );
});

test("edge, transport and router failures are never eligible for deletion", () => {
  const expected = "a".repeat(64);
  const refused = [
    [0, ""],
    ["000", ""],
    [403, "<html>forbidden</html>"],
    [502, "<html>bad gateway</html>"],
    [404, '{"error":"not-found","detail":"user worker not found"}'],
    [200, "<html>login</html>"],
  ];
  for (const [status, body] of refused) {
    assert.equal(classify(status, body, "", expected), "refuse");
  }
});

test("each stale function is delete-recreated one at a time and verified before advancing", () => {
  assert.match(recovery, /^set -euo pipefail$/m);
  assert.doesNotMatch(recovery, /set \+e/);
  const recoverOne = recovery.match(/recover_one\(\) \{([\s\S]*?)\n\}/)[1];
  const deleteAt = recoverOne.indexOf('functions delete "$name"');
  const deployAt = recoverOne.indexOf('functions deploy "$name"');
  const verifyAt = recoverOne.indexOf('require_expected_build "$name" "$expected"');
  assert.ok(deleteAt >= 0);
  assert.ok(deployAt > deleteAt);
  assert.ok(verifyAt > deployAt);
  const loop = recovery.match(/for fn in "\$\{RECOVERY_FUNCTIONS\[@\]\}"; do\n([\s\S]*?)\ndone/)[1];
  assert.match(loop.trim(), /^recover_one "\$fn"$/);
});

test("recovery is exact-main, owner-session and explicit-action gated", () => {
  assert.match(recovery, /fixlist_require_exact_main "\$REPO_ROOT" "\$SOURCE_SHA" "\$CONFIRM"/);
  assert.match(recovery, /fixlist_require_base44_owner "\$BASE44_EXPECTED_OWNER"/);
  assert.match(recovery, /RECREATE-STALE-BASE44-RELEASE-FUNCTIONS/);
  assert.match(recovery, /generate_release_contracts\.mjs" --check/);
  assert.match(recovery, /base44_release_manifest\.mjs" verify/);
});

test("recovery cannot widen into unrelated production mutation", () => {
  assert.doesNotMatch(recovery, /\bsite\s+deploy\b/);
  assert.doesNotMatch(recovery, /\bsecrets\s+set\b/);
  assert.doesNotMatch(recovery, /--force/);
  assert.doesNotMatch(recovery, /gcloud\s/);
});

test("workflow is owner-dispatched from exact main and passes both confirmations", () => {
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /test "\$INPUT_CONFIRM" = "\$source_sha"/);
  assert.match(workflow, /RECREATE-STALE-BASE44-RELEASE-FUNCTIONS/);
  assert.match(workflow, /environment: fixlist-production-owner/);
  assert.match(workflow, /authenticate-base44-owner-session\.sh/);
  assert.match(workflow, /recover-base44-stale-release-functions\.sh/);
  assert.match(workflow, /rm -rf "\$HOME\/\.base44"/);
});
