import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import test from "node:test";

const SCRIPT = "scripts/recover-base44-stale-v3-runtime.sh";
const WORKFLOW = ".github/workflows/fixlist-base44-v3-runtime-recovery.yml";
const ROUTE_FILE = "data/base44-function-routes.json";

const V3 = [
  "startStandardScanJobV3",
  "durableScanWorkerControlV3",
  "persistDurableScanAuthorityV3",
  "persistLimitedScanResultV3",
  "getCustomerScanResultV3",
  "deleteCustomerScanDataV3",
];

const routes = JSON.parse(fs.readFileSync(ROUTE_FILE, "utf8")).routes;
const canonicalOf = (alias) => Object.entries(routes).find(([, active]) => active === alias)?.[0];
const expectedBuild = Object.fromEntries(V3.map((name) => [name,
  execFileSync("node", ["scripts/generate_release_contracts.mjs", "--build-id", name], { encoding: "utf8" }).trim()]));
const expectedActivation = Object.fromEntries(V3.map((name) => [name,
  execFileSync("node", ["scripts/generate_release_contracts.mjs", "--activation-id", name], { encoding: "utf8" }).trim()]));
const staleActivation = Object.fromEntries(V3.map((name) => [name, `${name}-fresh-20260907-v1`]));

function handlerBody(name, buildId, activationId) {
  if (name === "startStandardScanJobV3") {
    return JSON.stringify({
      success: false,
      version: "startStandardScanJob_v3_server_admission",
      build_id: buildId,
      runtime_activation_id: activationId,
      error: "Method not allowed.",
    });
  }
  const message = {
    durableScanWorkerControlV3: "Use POST for durable worker control.",
    persistDurableScanAuthorityV3: "Use POST to persist durable scan authority.",
    persistLimitedScanResultV3: "Use POST to persist a limited scan result.",
    getCustomerScanResultV3: "Use POST to load a saved scan.",
    deleteCustomerScanDataV3: "Use POST to manage saved scan history.",
  }[name];
  return JSON.stringify({
    success: false,
    error_code: "method_not_allowed",
    error: message,
    build_id: buildId,
    runtime_activation_id: activationId,
  });
}

function classify(name, { status = 405, body, buildId, activationId }) {
  const out = execFileSync("bash", ["-c", [
    'FIXLIST_V3_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"',
    'resolve_v3_expectations "$1" >/dev/null 2>&1 || { echo resolve-refused; exit 0; }',
    'PROBE_STATUS="$2"',
    'PROBE_BODY="$3"',
    'PROBE_BUILD_ID="$4"',
    'PROBE_ACTIVATION_ID="$5"',
    'if route_reaches_json_handler && route_serves_expected_v3_runtime "$V3_EXPECTED_BUILD" "$V3_EXPECTED_ACTIVATION"; then echo current',
    'elif route_is_known_stale_v3 "$1" "$V3_CANONICAL" "$V3_STALE_ACTIVATION"; then echo stale',
    'else echo refuse',
    'fi',
  ].join("; "), SCRIPT, name, String(status), body ?? "", buildId ?? "", activationId ?? ""],
  { encoding: "utf8" });
  return out.trim();
}

test("all V3 routes have a fresh report-evidence activation distinct from the stale generation", () => {
  for (const name of V3) {
    assert.match(expectedActivation[name], /-report-evidence-20260909-v1$/);
    assert.notEqual(expectedActivation[name], staleActivation[name]);
    assert.ok(canonicalOf(name), `${name} must resolve through the active route contract`);
  }
});

test("matching build with the stale September 7 activation is still stale", () => {
  for (const name of V3) {
    assert.equal(classify(name, {
      body: handlerBody(name, expectedBuild[name], staleActivation[name]),
      buildId: expectedBuild[name],
      activationId: staleActivation[name],
    }), "stale", name);
  }
});

test("exact build plus exact activation is current and must not be deleted", () => {
  for (const name of V3) {
    assert.equal(classify(name, {
      body: handlerBody(name, expectedBuild[name], expectedActivation[name]),
      buildId: expectedBuild[name],
      activationId: expectedActivation[name],
    }), "current", name);
  }
});

test("old build with the known stale activation is recoverable", () => {
  const oldBuild = "a".repeat(64);
  for (const name of V3) {
    assert.notEqual(oldBuild, expectedBuild[name]);
    assert.equal(classify(name, {
      body: handlerBody(name, oldBuild, staleActivation[name]),
      buildId: oldBuild,
      activationId: staleActivation[name],
    }), "stale", name);
  }
});

test("ambiguous or malformed runtime states refuse deletion", () => {
  const name = "getCustomerScanResultV3";
  const goodBody = handlerBody(name, expectedBuild[name], staleActivation[name]);
  const cases = [
    ["transport", { status: 0, body: "", buildId: "", activationId: "" }],
    ["router 404", { status: 404, body: JSON.stringify({ error: "Not found" }), buildId: "", activationId: "" }],
    ["html edge", { status: 502, body: "<html>bad gateway</html>", buildId: "", activationId: "" }],
    ["unknown activation", { body: goodBody, buildId: expectedBuild[name], activationId: "unknown-v9" }],
    ["new marker old build", { body: handlerBody(name, "a".repeat(64), expectedActivation[name]), buildId: "a".repeat(64), activationId: expectedActivation[name] }],
    ["missing build", { body: handlerBody(name, "", staleActivation[name]), buildId: "", activationId: staleActivation[name] }],
    ["wrong route body", { body: handlerBody("durableScanWorkerControlV3", expectedBuild[name], staleActivation[name]), buildId: expectedBuild[name], activationId: staleActivation[name] }],
  ];
  for (const [label, probe] of cases) {
    assert.equal(classify(name, probe), "refuse", label);
  }
});

test("recovery script is exact-main, all-six-preflight, one-at-a-time and non-deployment scoped", () => {
  const body = fs.readFileSync(SCRIPT, "utf8");
  assert.match(body, /V3_EXPECTED_ACTION_CONFIRM="RECREATE-STALE-BASE44-V3-RUNTIME"/);
  assert.match(body, /fixlist_require_exact_main "\$REPO_ROOT" "\$SOURCE_SHA" "\$CONFIRM"/);
  assert.match(body, /generate_release_contracts\.mjs" --check/);
  assert.match(body, /base44_release_manifest\.mjs" verify/);
  assert.match(body, /preflight_all_v3_routes/);
  assert.match(body, /functions delete "\$name"/);
  assert.match(body, /functions deploy "\$name"/);
  assert.match(body, /still present after delete/);
  assert.match(body, /did not reappear after deploy/);
  assert.match(body, /require_expected_v3_runtime/);
  assert.doesNotMatch(body, /site deploy/);
  assert.doesNotMatch(body, /gcloud/);
  assert.doesNotMatch(body, /SCAN_TASKS_QUEUE|admission barrier|worker traffic/);
});

test("workflow requires exact SHA, owner device auth and destructive confirmation", () => {
  const body = fs.readFileSync(WORKFLOW, "utf8");
  assert.match(body, /workflow_dispatch:/);
  assert.match(body, /github\.actor == 'bright4862-design'/);
  assert.match(body, /fixlist-base44-hosted-controls-v2/);
  assert.match(body, /test "\$INPUT_CONFIRM" = "\$source_sha"/);
  assert.match(body, /RECREATE-STALE-BASE44-V3-RUNTIME/);
  assert.match(body, /authenticate-base44-owner-session\.sh/);
  assert.match(body, /recover-base44-stale-v3-runtime\.sh/);
  assert.match(body, /verify-base44-functions\.sh/);
  assert.doesNotMatch(body, /deploy-base44-beta-site\.sh/);
  assert.doesNotMatch(body, /build-worker-candidate|promote-staged-worker/);
});
