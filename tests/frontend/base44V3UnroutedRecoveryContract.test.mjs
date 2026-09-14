import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const scriptPath = "scripts/recover-base44-unrouted-v3-release-functions.sh";
const workflowPath = ".github/workflows/fixlist-base44-v3-unrouted-recovery.yml";

const RECOVERABLE = [
  "ownerScanDebugControl",
  "startStandardScanJobV3",
  "durableScanWorkerControlV3",
  "persistDurableScanAuthorityV3",
  "persistLimitedScanResultV3",
  "getCustomerScanResultV3",
  "deleteCustomerScanDataV3",
  "createAccessCheckout",
  "stripeWebhook",
];

function load(path) {
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

function executable(source) {
  return source
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");
}

function arrayLiteral(source, name) {
  const match = source.match(new RegExp(`${name}=\\(([^)]*)\\)`));
  assert.ok(match, `${name} array not found`);
  return match[1].split("\n").map((line) => line.trim()).filter(Boolean);
}

test("a dedicated V3 router-loss recovery lane exists", () => {
  assert.ok(existsSync(scriptPath), `${scriptPath} must exist`);
  assert.ok(existsSync(workflowPath), `${workflowPath} must exist`);
});

test("the lane is limited to the nine release-critical functions and starts with the owner-only canary", () => {
  const script = load(scriptPath);
  if (!script) return;
  assert.deepEqual(arrayLiteral(script, "RECOVERY_FUNCTIONS"), RECOVERABLE);
  assert.equal(arrayLiteral(script, "RECOVERY_FUNCTIONS")[0], "ownerScanDebugControl");
});

test("router-level 404 is the only broken pre-state eligible for deletion", () => {
  const script = load(scriptPath);
  if (!script) return;
  assert.match(script, /ROUTER_MISSING_MARKER="user worker not found"/);
  assert.match(script, /route_is_unregistered/);
  assert.match(script, /preflight_all_routes/);

  const body = script.slice(script.indexOf("recover_one() {"));
  const guardAt = body.indexOf("route_is_unregistered");
  const deleteAt = body.indexOf("functions delete");
  assert.ok(guardAt >= 0, "recover_one must prove the router-level 404");
  assert.ok(deleteAt >= 0, "recover_one must delete only inside the guarded path");
  assert.ok(guardAt < deleteAt, "router-level 404 proof must happen before deletion");
});

test("each function is recreated one at a time and attested before the next", () => {
  const script = load(scriptPath);
  if (!script) return;
  assert.match(script, /still present after delete/);
  assert.match(script, /did not reappear after deploy/);
  assert.match(script, /require_expected_route "\$name"/);
  assert.match(script, /verify-base44-functions\.sh/);
});

test("recovery is exact-main owner-only and cannot publish the site or alter release state", () => {
  const script = load(scriptPath);
  if (!script) return;
  const code = executable(script);
  assert.match(script, /fixlist_require_exact_main/);
  assert.match(script, /fixlist_require_base44_owner/);
  assert.match(script, /RECREATE-UNROUTED-BASE44-V3-RELEASE-FUNCTIONS/);
  assert.match(script, /base44_release_manifest\.mjs" verify/);
  assert.doesNotMatch(code, /site deploy/);
  assert.doesNotMatch(code, /--force/);
  assert.doesNotMatch(code, /secrets set/);
  assert.doesNotMatch(code, /fixlist_set_base44_release_source_sha/);
  assert.doesNotMatch(code, /entities\s+push/);
  assert.doesNotMatch(code, /barrier|acceptance|cohort/i);
});

test("the hosted workflow requires Bright, main, exact SHA, and the destructive confirmation", () => {
  const workflow = load(workflowPath);
  if (!workflow) return;
  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /RECREATE-UNROUTED-BASE44-V3-RELEASE-FUNCTIONS/);
  assert.match(workflow, /fixlist-production-owner/);
  assert.match(workflow, /recover-base44-unrouted-v3-release-functions\.sh/);
});
