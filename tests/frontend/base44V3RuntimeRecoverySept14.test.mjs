import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import test from "node:test";

const SCRIPT = "scripts/recover-base44-stale-v3-runtime.sh";
const ROUTE_FILE = "data/base44-function-routes.json";

const observedSept14 = {
  startStandardScanJobV3: "7a121e334ea8944504e5f5ebdb7bec7dfc8efd6e8fbfa89995bb0cad0dac6771",
  durableScanWorkerControlV3: "61f7d18336f29b514be3727b087bd7187eff65c634e11c3760faea9f9d45ebec",
  persistDurableScanAuthorityV3: "f177c20c256b736e954f49c1cdcbadbc72cea35c904e97c933c2156ffcc5ad91",
  persistLimitedScanResultV3: "c22ee54343fc4717abd0ff8a7eab936cf7f7ccb102c851c7378aebd7b4c11db0",
  getCustomerScanResultV3: "dd8df0224006a5709207c9169025792908bf3c1b1e4b1db82478ae2f0c4ce350",
};

const routeContract = JSON.parse(fs.readFileSync(ROUTE_FILE, "utf8"));
const v3Routes = routeContract.generation === "v3"
  ? routeContract.routes
  : routeContract.historical_routes?.v3 || {};
const canonicalOf = (alias) => Object.entries(v3Routes).find(([, route]) => route === alias)?.[0];
const expectedActivation = Object.fromEntries(Object.keys(observedSept14).map((name) => [name,
  execFileSync("node", ["scripts/generate_release_contracts.mjs", "--activation-id", name], { encoding: "utf8" }).trim()]));

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
  }[name];
  return JSON.stringify({
    success: false,
    error_code: "method_not_allowed",
    error: message,
    build_id: buildId,
    runtime_activation_id: activationId,
  });
}

function classify(name, buildId) {
  const activationId = expectedActivation[name];
  const body = handlerBody(name, buildId, activationId);
  return execFileSync("bash", ["-c", [
    'FIXLIST_V3_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"',
    'resolve_v3_expectations "$1" >/dev/null 2>&1 || { echo resolve-refused; exit 0; }',
    'PROBE_STATUS=405',
    'PROBE_BODY="$2"',
    'PROBE_BUILD_ID="$3"',
    'PROBE_ACTIVATION_ID="$4"',
    'if route_is_known_stale_v3 "$1" "$V3_CANONICAL" "$V3_STALE_ACTIVATION"; then echo stale; else echo refuse; fi',
  ].join("; "), SCRIPT, name, body, buildId, activationId], { encoding: "utf8" }).trim();
}

test("the exact Sep 14 preview-cutover stale V3 builds are recoverable", () => {
  for (const [name, buildId] of Object.entries(observedSept14)) {
    assert.ok(canonicalOf(name), `${name} must resolve through the exact V3 route contract`);
    assert.equal(classify(name, buildId), "stale", name);
  }
});

test("nearby unknown builds with the current activation remain refused", () => {
  for (const name of Object.keys(observedSept14)) {
    assert.equal(classify(name, "a".repeat(64)), "refuse", name);
  }
});
