import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import test from "node:test";

const SCRIPT = "scripts/recover-base44-stale-release-functions.sh";
const WORKFLOW = ".github/workflows/fixlist-base44-stale-function-recovery.yml";
const recovery = fs.readFileSync(SCRIPT, "utf8");
const workflow = fs.readFileSync(WORKFLOW, "utf8");

function classify(name, status, body, buildId, expected) {
  const out = execFileSync(
    "bash",
    [
      "-c",
      [
        'FIXLIST_STALE_RECOVERY_LIB_ONLY=1 source "$0"',
        'PROBE_STATUS="$2"',
        'PROBE_BODY="$3"',
        'PROBE_BUILD_ID="$4"',
        'if route_reaches_json_handler && route_serves_expected_build "$5"; then echo exact',
        'elif route_is_known_stale_handler "$1"; then echo stale',
        'else echo refuse',
        'fi',
      ].join("; "),
      SCRIPT,
      name,
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
    classify(
      "startStandardScanJob",
      405,
      '{"success":false,"version":"startStandardScanJob_v3_server_admission","error":"Method not allowed.","build_id":"' + expected + '"}',
      expected,
      expected,
    ),
    "exact",
  );
  assert.equal(
    classify(
      "startStandardScanJob",
      405,
      '{"success":false,"version":"startStandardScanJob_v3_server_admission","error":"Method not allowed."}',
      "",
      expected,
    ),
    "stale",
  );
  assert.equal(
    classify(
      "startStandardScanJob",
      405,
      '{"success":false,"version":"startStandardScanJob_v3_server_admission","error":"Method not allowed.","build_id":"' + "b".repeat(64) + '"}',
      "b".repeat(64),
      expected,
    ),
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
    assert.equal(classify("startStandardScanJob", status, body, "", expected), "refuse");
  }
});

test("only the proven live stale signatures are eligible for deletion", () => {
  const expected = "a".repeat(64);
  const stale = [
    ["startStandardScanJob", 405, '{"success":false,"version":"startStandardScanJob_v3_server_admission","error":"Method not allowed."}'],
    ["durableScanWorkerControl", 405, '{"success":false,"error_code":"method_not_allowed","error":"Use POST for durable worker control."}'],
    ["persistDurableScanAuthority", 405, '{"success":false,"error_code":"method_not_allowed","error":"Use POST to persist durable scan authority."}'],
    ["persistLimitedScanResult", 405, '{"success":false,"error_code":"method_not_allowed","error_message":"Use POST to persist a limited scan result."}'],
    ["getCustomerScanResult", 405, '{"success":false,"error_code":"method_not_allowed","error":"Use POST to load a saved scan."}'],
    ["deleteCustomerScanData", 405, '{"success":false,"error_code":"method_not_allowed","error":"Use POST to manage saved scan history."}'],
    ["ownerScanDebugControl", 405, '{"success":false,"error_code":"method_not_allowed","error":"Use POST for owner scan controls."}'],
    ["createAccessCheckout", 500, '{"error":"Checkout is temporarily unavailable.","code":"checkout_failed"}'],
    ["stripeWebhook", 400, '{"error":"Neither apiKey nor config.authenticator provided"}'],
  ];
  for (const [name, status, body] of stale) {
    assert.equal(classify(name, status, body, "", expected), "stale", name);
  }

  assert.equal(
    classify("createAccessCheckout", 500, '{"error":"unrelated"}', "", expected),
    "refuse",
  );
  assert.equal(
    classify("stripeWebhook", 403, '{"error":"forbidden"}', "", expected),
    "refuse",
  );
  assert.equal(
    classify("startStandardScanJob", 404, '{"error":"not-found","detail":"app not found"}', "", expected),
    "refuse",
  );
});

test("all nine are preflighted before the first delete and each recovery is verified before advancing", () => {
  assert.match(recovery, /^set -euo pipefail$/m);
  assert.doesNotMatch(recovery, /set \+e/);

  const preflight = recovery.match(/require_recoverable_prestate\(\) \{([\s\S]*?)\n\}/)[1];
  assert.match(preflight, /valid_build_id "\$expected"/);
  assert.match(preflight, /probe_route "\$name"/);
  assert.match(preflight, /route_is_known_stale_handler "\$name"/);

  const recoverOne = recovery.match(/recover_one\(\) \{([\s\S]*?)\n\}/)[1];
  const validateAt = recoverOne.indexOf('valid_build_id "$expected"');
  const probeAt = recoverOne.indexOf('probe_route "$name"');
  const deleteAt = recoverOne.indexOf('functions delete "$name"');
  const deployAt = recoverOne.indexOf('functions deploy "$name"');
  const verifyAt = recoverOne.indexOf('require_expected_build "$name" "$expected"');
  assert.ok(validateAt >= 0, "expected build ID must be validated");
  assert.ok(probeAt > validateAt, "build ID validation must happen before stale classification");
  assert.ok(deleteAt > probeAt);
  assert.ok(deployAt > deleteAt);
  assert.ok(verifyAt > deployAt);

  const preflightBannerAt = recovery.indexOf("BASE44_STALE_RECOVERY_PREFLIGHT_VERIFIED");
  const firstDeleteAt = recovery.indexOf('functions delete "$name"');
  assert.ok(preflightBannerAt >= 0);
  assert.ok(preflightBannerAt < firstDeleteAt, "all-nine preflight must complete before any delete path is reachable");

  const loops = [...recovery.matchAll(/for fn in "\$\{RECOVERY_FUNCTIONS\[@\]\}"; do\n([\s\S]*?)\ndone/g)];
  const preflightLoop = loops.find((match) => match[1].trim() === 'require_recoverable_prestate "$fn"');
  const recoveryLoop = loops.find((match) => match[1].trim() === 'recover_one "$fn"');
  assert.ok(preflightLoop, "the driver must preflight every release function");
  assert.ok(recoveryLoop, "the recovery driver must call recover_one bare under set -e");
});

test("recovery is exact-main, owner-session and explicit-action gated", () => {
  assert.match(recovery, /fixlist_require_exact_main "\$REPO_ROOT" "\$SOURCE_SHA" "\$CONFIRM"/);
  assert.match(recovery, /fixlist_require_base44_owner "\$BASE44_EXPECTED_OWNER"/);
  assert.match(recovery, /RECREATE-STALE-BASE44-RELEASE-FUNCTIONS/);
  assert.match(recovery, /generate_release_contracts\.mjs" --check/);
  assert.match(recovery, /base44_release_manifest\.mjs" verify/);
  assert.match(recovery, /valid_build_id\(\)/);
  assert.match(recovery, /Refusing final verification: expected build id for \$fn is not a 64-hex digest/);
});

test("recovery cannot widen into unrelated production mutation", () => {
  const executable = recovery
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("#"))
    .join("\n");
  assert.doesNotMatch(executable, /\bsite\s+deploy\b/);
  assert.doesNotMatch(executable, /\bsecrets\s+set\b/);
  assert.doesNotMatch(executable, /--force/);
  assert.doesNotMatch(executable, /gcloud\s/);
});

test("workflow is owner-dispatched from exact main and passes both confirmations", () => {
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /ACTOR: \$\{\{ github\.actor \}\}/);
  assert.match(workflow, /REF: \$\{\{ github\.ref \}\}/);
  assert.match(workflow, /SHA: \$\{\{ github\.sha \}\}/);
  assert.match(workflow, /test "\$ACTOR" = "bright4862-design"/);
  assert.match(workflow, /test "\$REF" = "refs\/heads\/main"/);
  assert.doesNotMatch(workflow, /test "\$\{\{ github\.(actor|ref|sha) \}\}"/);
  assert.match(workflow, /test "\$INPUT_CONFIRM" = "\$source_sha"/);
  assert.match(workflow, /RECREATE-STALE-BASE44-RELEASE-FUNCTIONS/);
  assert.match(workflow, /environment: fixlist-production-owner/);
  assert.match(workflow, /authenticate-base44-owner-session\.sh/);
  assert.match(workflow, /recover-base44-stale-release-functions\.sh/);
  assert.match(workflow, /rm -rf "\$HOME\/\.base44"/);
});
