import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const SCRIPT = "scripts/recover-base44-stale-release-functions.sh";
const WORKFLOW = ".github/workflows/fixlist-base44-stale-function-recovery.yml";
const recovery = fs.readFileSync(SCRIPT, "utf8");
const workflow = fs.readFileSync(WORKFLOW, "utf8");
const ownerDebugEntry = fs.readFileSync("base44/functions/ownerScanDebugControl/entry.ts", "utf8");
const ownerDebugBuildSource = fs.readFileSync("base44/functions/ownerScanDebugControl/generatedBuildId.js", "utf8");
const ownerDebugBuildId = ownerDebugBuildSource.match(/FUNCTION_BUILD_ID = "([0-9a-f]{64})"/)?.[1] || "";

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


async function invokeOwnerDebugGet() {
  assert.match(ownerDebugBuildId, /^[0-9a-f]{64}$/);

  let handler = null;
  const source = ownerDebugEntry
    .replace(
      'import { createClientFromRequest } from "npm:@base44/sdk@0.8.41";',
      'const createClientFromRequest = () => { throw new Error("POST path must not run"); };',
    )
    .replace(
      'import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "./generatedReleaseContract.js";',
      'const RELEASE_COMPONENT_VERSIONS = { admission_reconciliation_version: "test" }; const RELEASE_FINGERPRINT = "68a16802a9c7a543";',
    )
    .replace(
      'import { FUNCTION_BUILD_ID } from "./generatedBuildId.js";',
      `const FUNCTION_BUILD_ID = "${ownerDebugBuildId}";`,
    )
    .replace(
      'import { persistExactRelease } from "./admissionRelease.js";',
      'const persistExactRelease = async () => { throw new Error("POST path must not run"); };',
    );

  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.None,
    },
  }).outputText;

  vm.runInNewContext(compiled, {
    Deno: {
      env: { get: () => "" },
      serve: (candidate) => { handler = candidate; },
    },
    Request,
    Response,
    TextEncoder,
    clearTimeout,
    console,
    crypto: globalThis.crypto,
    fetch,
    setTimeout,
  });

  assert.equal(typeof handler, "function");
  return handler(new Request("https://example.invalid", { method: "GET" }));
}

test("owner debug GET runtime returns the activation marker and exact generated build identity", async () => {
  const response = await invokeOwnerDebugGet();
  assert.equal(response.status, 405);
  const body = await response.json();
  assert.equal(body.runtime_activation_id, "owner-debug-sandbox-activation-20260903-v1");
  assert.equal(body.build_id, ownerDebugBuildId);
  assert.equal(body.error_code, "method_not_allowed");
});

test("every remaining release function carries a runtime reactivation marker in its probe response", () => {
  const targets = [
    ["durableScanWorkerControl", "base44/functions/durableScanWorkerControl/entry.ts", "durable-worker-prod-reactivation-20260903-v1"],
    ["persistDurableScanAuthority", "base44/functions/persistDurableScanAuthority/entry.ts", "durable-authority-prod-reactivation-20260903-v1"],
    ["persistLimitedScanResult", "base44/functions/persistLimitedScanResult/entry.ts", "limited-result-prod-reactivation-20260903-v1"],
    ["deleteCustomerScanData", "base44/functions/deleteCustomerScanData/index.ts", "delete-history-prod-reactivation-20260903-v1"],
    ["getCustomerScanResult", "base44/functions/getCustomerScanResult/entry.ts", "customer-result-prod-reactivation-20260903-v1"],
    ["startStandardScanJob", "base44/functions/startStandardScanJob/entry.ts", "start-standard-prod-reactivation-20260903-v1"],
    ["createAccessCheckout", "base44/functions/createAccessCheckout/entry.ts", "checkout-prod-reactivation-20260903-v1"],
    ["stripeWebhook", "base44/functions/stripeWebhook/entry.ts", "stripe-webhook-prod-reactivation-20260903-v1"],
  ];

  for (const [name, sourcePath, marker] of targets) {
    const source = fs.readFileSync(sourcePath, "utf8");
    const buildSource = fs.readFileSync(`base44/functions/${name}/generatedBuildId.js`, "utf8");
    assert.ok(source.includes(`BASE44_RUNTIME_ACTIVATION_ID = "${marker}"`), name);
    assert.match(source, /runtime_activation_id:\s*BASE44_RUNTIME_ACTIVATION_ID/, name);
    assert.match(buildSource, /FUNCTION_BUILD_ID = "[0-9a-f]{64}"/, name);
  }

  const deleteEntry = fs.readFileSync("base44/functions/deleteCustomerScanData/entry.ts", "utf8");
  assert.match(deleteEntry, /export const BASE44_RUNTIME_ACTIVATION_ID = "delete-history-prod-reactivation-20260903-v1";/);
});

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
  assert.equal(
    classify(
      "durableScanWorkerControl",
      405,
      '{"success":false,"error_code":"method_not_allowed"}',
      "",
      expected,
    ),
    "refuse",
    "generic method_not_allowed JSON must not authorize deletion",
  );
  assert.equal(
    classify(
      "durableScanWorkerControl",
      405,
      '<html>{"success":false,"error_code":"method_not_allowed","error":"Use POST for durable worker control."}</html>',
      "",
      expected,
    ),
    "refuse",
    "a complete stale signature embedded in non-JSON content must not authorize deletion",
  );
  assert.equal(
    classify(
      "durableScanWorkerControl",
      405,
      '{"success":false,"error_code":"method_not_allowed","error":"Use POST for durable worker control."',
      "",
      expected,
    ),
    "refuse",
    "malformed JSON must not authorize deletion",
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

  const loops = [...recovery.matchAll(/for fn in "\$\{RECOVERY_FUNCTIONS\[@\]\}"; do\n([\s\S]*?)\ndone/g)];
  const preflightLoopIndex = loops.findIndex((match) => match[1].trim() === 'require_recoverable_prestate "$fn"');
  const recoveryLoopIndex = loops.findIndex((match) => match[1].trim() === 'recover_one "$fn"');
  assert.ok(preflightLoopIndex >= 0, "the driver must preflight every release function");
  assert.ok(recoveryLoopIndex >= 0, "the recovery driver must call recover_one bare under set -e");
  assert.ok(
    preflightLoopIndex < recoveryLoopIndex,
    "the all-nine preflight loop must execute before the first recovery loop",
  );
  assert.match(recovery, /BASE44_STALE_RECOVERY_PREFLIGHT_VERIFIED/);
});

test("recovery is exact-main, owner-session and explicit-action gated", () => {
  assert.match(recovery, /fixlist_require_exact_main "\$REPO_ROOT" "\$SOURCE_SHA" "\$CONFIRM"/);
  assert.match(recovery, /fixlist_require_base44_owner "\$BASE44_EXPECTED_OWNER"/);
  assert.match(recovery, /RECREATE-STALE-BASE44-RELEASE-FUNCTIONS/);
  assert.match(recovery, /generate_release_contracts\.mjs" --check/);
  assert.match(recovery, /base44_release_manifest\.mjs" verify/);
  assert.match(recovery, /valid_build_id\(\)/);
  assert.match(recovery, /probe_body_is_json_object\(\)/);
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
  const installAt = workflow.indexOf("Install exact frontend dependencies");
  const loginAt = workflow.indexOf("Authenticate Base44 owner with ephemeral device code");
  assert.ok(installAt >= 0 && loginAt >= 0);
  assert.ok(installAt < loginAt, "npm ci must complete before the owner session is established");
  assert.match(workflow, /recover-base44-stale-release-functions\.sh/);
  assert.match(workflow, /rm -rf "\$HOME\/\.base44"/);
});
