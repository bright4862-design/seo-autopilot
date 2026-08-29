import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import test from "node:test";

// These exercise the real bash classifiers, not the script's text. The probe is
// the only thing standing between "the route came back" and "an edge returned
// something", and an over-broad probe lets the run delete the next function
// while the previous one is still dead -- so the classification is asserted
// against actual response shapes.
const SCRIPT = "scripts/recover-base44-unrouted-functions.sh";
const recovery = readFileSync(SCRIPT, "utf8");

function classify(predicate, status, body) {
  const out = execFileSync(
    "bash",
    [
      "-c",
      `FIXLIST_RECOVERY_LIB_ONLY=1 source "$0"; PROBE_STATUS="$1"; PROBE_BODY="$2"; ` +
        `if ${predicate}; then echo yes; else echo no; fi`,
      SCRIPT,
      String(status),
      body,
    ],
    { encoding: "utf8" },
  );
  return out.trim() === "yes";
}

const isRecovered = (status, body) => classify("route_is_recovered", status, body);
const reachesHandler = (status, body) => classify("route_reaches_handler", status, body);
const isUnregistered = (status, body) => classify("route_is_unregistered", status, body);

// The exact shape all five recovery handlers emit. Each rejects GET as the first
// statement in Deno.serve -- before any try/catch or env access -- through
// Response.json({success:false, error_code:"method_not_allowed", ...},{status:405}).
// persistLimitedScanResult names the prose field error_message rather than
// error, so error_code is the field the probe keys on.
const HANDLER_405 = {
  ownerScanDebugControl:
    '{"success":false,"error_code":"method_not_allowed","error":"Use POST for owner scan controls."}',
  durableScanWorkerControl:
    '{"success":false,"error_code":"method_not_allowed","error":"Use POST for durable worker control."}',
  persistDurableScanAuthority:
    '{"success":false,"error_code":"method_not_allowed","error":"Use POST to persist durable scan authority."}',
  persistLimitedScanResult:
    '{"success":false,"error_code":"method_not_allowed","error_message":"Use POST to persist a limited scan result."}',
  deleteCustomerScanData:
    '{"success":false,"error_code":"method_not_allowed","error":"Use POST to manage saved scan history."}',
};

const ROUTER_404 = '{"error":"not-found","detail":"user worker not found"}';

test("the handler 405 signature counts as recovered, for every one of the five", () => {
  for (const [name, body] of Object.entries(HANDLER_405)) {
    assert.equal(isRecovered(405, body), true, `${name} 405 must count as recovered`);
  }
});

test("the router 404 is never recovered", () => {
  assert.equal(isRecovered(404, ROUTER_404), false);
  assert.equal(isUnregistered(404, ROUTER_404), true);
  assert.equal(reachesHandler(404, ROUTER_404), false);
});

test("edge and error responses are never mistaken for a live handler", () => {
  const notHandler = [
    [403, "<html><head><title>403 Forbidden</title></head><body>cloudflare</body></html>"],
    [403, '{"error":"forbidden"}'],
    [500, "<html>500 Internal Server Error</html>"],
    [500, '{"error":"internal"}'],
    [502, "<html>Bad Gateway</html>"],
    [503, "Service Unavailable"],
    [404, '{"error":"not-found","detail":"app not found"}'],
    [301, ""],
    [302, ""],
    [200, "<!doctype html><html>login page</html>"],
    [0, ""],
    ["000", ""],
  ];
  for (const [status, body] of notHandler) {
    assert.equal(
      isRecovered(status, body),
      false,
      `HTTP ${status} ${body.slice(0, 30)} must not count as recovered`,
    );
  }
  // None of these is the exact router 404 either, so recover_one treats them as
  // an unknown pre-state and refuses rather than deleting.
  for (const [status, body] of notHandler) {
    assert.equal(isUnregistered(status, body), false, `HTTP ${status} must not read as unregistered`);
  }
});

test("a 405 that is not the handler's own 405 is not recovered", () => {
  // An edge or gateway can answer 405 without ever reaching the function.
  assert.equal(isRecovered(405, "<html><title>405 Not Allowed</title></html>"), false);
  assert.equal(isRecovered(405, '{"error":"method not allowed"}'), false);
  assert.equal(isRecovered(405, '{"success":true,"error_code":"method_not_allowed"}'), false);
  assert.equal(isRecovered(405, ""), false);
});

test("the marker text inside a non-object body is not the handler's response", () => {
  // An edge page that echoes the rejected payload, or any wrapper around it,
  // carries the same substrings without being the handler's JSON object. Only a
  // response that *is* that object counts, which is why the body must start
  // with `{` and not merely contain the fields somewhere.
  const echoed = '{"success":false,"error_code":"method_not_allowed"}';
  assert.equal(isRecovered(405, `<html><body>rejected ${echoed}</body></html>`), false);
  assert.equal(isRecovered(405, `[${echoed}]`), false);
  assert.equal(isRecovered(405, `error: ${echoed}`), false);
  assert.equal(reachesHandler(405, `<html>${echoed}</html>`), false);
});

test("protected liveness accepts each protected function's own GET answer", () => {
  // These four legitimately differ, which is why they use the weak predicate:
  // startStandardScanJob answers 405 with no error_code, createAccessCheckout
  // 500, stripeWebhook 400.
  assert.equal(
    reachesHandler(405, '{"success":false,"version":"startStandardScanJob_v3_server_admission","error":"Method not allowed."}'),
    true,
  );
  assert.equal(reachesHandler(405, HANDLER_405.deleteCustomerScanData), true);
  assert.equal(reachesHandler(500, '{"error":"Checkout is temporarily unavailable.","code":"checkout_failed"}'), true);
  assert.equal(reachesHandler(400, '{"error":"Neither apiKey nor config.authenticator provided"}'), true);
  // But it still rejects edge HTML and transport failure.
  assert.equal(reachesHandler(403, "<html>cloudflare</html>"), false);
  assert.equal(reachesHandler(502, "<html>Bad Gateway</html>"), false);
  assert.equal(reachesHandler("000", ""), false);
});

test("ownerScanDebugControl is still the canary and the five are unchanged", () => {
  const list = recovery.match(/RECOVERY_FUNCTIONS=\(([^)]*)\)/)[1]
    .split("\n").map((l) => l.trim()).filter(Boolean);
  assert.deepEqual(list, [
    "ownerScanDebugControl",
    "durableScanWorkerControl",
    "persistDurableScanAuthority",
    "persistLimitedScanResult",
    "deleteCustomerScanData",
  ]);
});

test("a protected function in the recovery set is refused before any network call", () => {
  // The copy has to sit in scripts/ because the script resolves REPO_ROOT from
  // its own location to source the release guards.
  const patched = "scripts/.recovery-protected-name.probe.sh";
  writeFileSync(
    patched,
    recovery.replace("RECOVERY_FUNCTIONS=(\n", "RECOVERY_FUNCTIONS=(\n  stripeWebhook\n"),
  );
  let stderr = "";
  let code = 0;
  try {
    execFileSync("bash", [patched], {
      encoding: "utf8",
      env: { ...process.env, BASE44_API_KEY: "", BASE44_EXPECTED_OWNER: "x", SOURCE_SHA: "x", CONFIRM: "x" },
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    code = error.status;
    stderr = String(error.stderr || "");
  } finally {
    rmSync(patched, { force: true });
  }
  assert.equal(code, 2, "a protected name in the recovery set must exit 2");
  assert.match(stderr, /stripeWebhook serves live traffic and must never be deleted/);
});

test("a failed probe stops the run before the next function is touched", () => {
  // recover_one returns non-zero when the probe never reaches the handler, and
  // the driver calls it bare under `set -e`, so the loop cannot advance.
  assert.match(recovery, /^set -euo pipefail$/m);
  assert.doesNotMatch(recovery, /set \+e/);
  const loop = recovery.match(/for fn in "\$\{RECOVERY_FUNCTIONS\[@\]\}"; do\n(.*?)\ndone/s)[1];
  assert.match(loop.trim(), /^recover_one "\$fn"$/, "recover_one must be called bare, not guarded");
  assert.doesNotMatch(loop, /\|\||&&|if /, "guarding the call would suppress set -e");
  assert.match(recovery, /require_handled_route "\$name"\n  RECOVERY_APPLIED/);
});

test("a dry run never reports functions as recovered", () => {
  assert.match(recovery, /BASE44_UNROUTED_FUNCTIONS_DRY_RUN_COMPLETE/);
  const dryBlock = recovery.match(/if \[\[ -n "\$DRY_RUN" \]\]; then\n\s*printf '\\nBASE44_UNROUTED[\s\S]*?\nfi/)[0];
  assert.match(dryBlock, /recovered=0/);
  assert.doesNotMatch(dryBlock, /BASE44_UNROUTED_FUNCTIONS_RECOVERED/);
  // The success banner reports what actually happened, not the list length.
  assert.match(recovery, /BASE44_UNROUTED_FUNCTIONS_RECOVERED[\s\S]*?"\$RECOVERY_APPLIED"/);
  assert.doesNotMatch(recovery, /BASE44_UNROUTED_FUNCTIONS_RECOVERED[\s\S]*?\$\{#RECOVERY_FUNCTIONS\[@\]\}/);
});
