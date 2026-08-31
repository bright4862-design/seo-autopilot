import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import {
  OWNER_SCAN_DEBUG_EMAIL,
  OWNER_SCAN_DEBUG_USER_ID,
  isOwnerScanDebugUser,
} from "../../src/lib/ownerScanDebugIdentity.js";

test("owner scan debug UI is restricted to the exact owner admin identity", () => {
  assert.equal(OWNER_SCAN_DEBUG_EMAIL, "bright4862@gmail.com");
  assert.equal(OWNER_SCAN_DEBUG_USER_ID, "6a498da58ef5cec1f5cd4486");
  assert.equal(isOwnerScanDebugUser({
    id: OWNER_SCAN_DEBUG_USER_ID,
    email: OWNER_SCAN_DEBUG_EMAIL,
    role: "admin",
  }), true);
  assert.equal(isOwnerScanDebugUser({
    id: OWNER_SCAN_DEBUG_USER_ID,
    email: OWNER_SCAN_DEBUG_EMAIL,
    role: "user",
  }), false);
  assert.equal(isOwnerScanDebugUser({
    id: "someone-else",
    email: OWNER_SCAN_DEBUG_EMAIL,
    role: "admin",
  }), false);
});

test("server kill control is separately gated and uses coordinator release/status", () => {
  const source = fs.readFileSync("base44/functions/ownerScanDebugControl/entry.ts", "utf8");
  assert.match(source, /bright4862@gmail\.com/);
  assert.match(source, /6a498da58ef5cec1f5cd4486/);
  assert.match(source, /role[^\n]+admin/i);
  assert.match(source, /attempt_count/);
  assert.match(source, /owner_manual_kill/);
  assert.match(source, /\/release/);
  assert.match(source, /\/status/);
  assert.match(source, /release_gate_eligible:\s*false/);
  assert.match(source, /function coordinatorLeaseReleased/);
  assert.match(source, /sanitizeAdmissionResult\(result\)/);
  assert.match(source, /admission_release_state/);
  assert.match(source, /admission_release_coordinator_request_id/);
  assert.match(source, /ADMISSION_RECONCILIATION_VERSION/);
  assert.match(source, /COORDINATOR_TIMEOUT_MS/);
  assert.match(source, /persistExactRelease/);
  assert.doesNotMatch(source, /lease_released:\s*admission\.ok\s*===\s*true\s*&&\s*admission\.lease_active/);
  assert.doesNotMatch(source, /return admission\.ok === true && admission\.lease_active === false/);
});

test("customer FixList does not embed owner debug or kill controls", () => {
  const source = fs.readFileSync("src/pages/FixList.jsx", "utf8");
  assert.doesNotMatch(source, /Owner debug/);
  assert.doesNotMatch(source, /Debug scan/);
  assert.doesNotMatch(source, /Force stop scan/);
  assert.doesNotMatch(source, /ownerScanDebugControl/);
  assert.doesNotMatch(source, /isOwnerScanDebugUser/);
  assert.doesNotMatch(source, /ownerDebugResult/);
  assert.doesNotMatch(source, /AuthContext/);
  assert.doesNotMatch(source, /\buseAuth\b/);
});

// These three were pre-existing defects in the handler this release moved from
// index.ts into the routed entry module. They matter more here than their
// severity labels suggest: this is the tool an owner opens when a scan is
// stuck, so a discarded failure reason and an unbounded read are failures of
// the diagnostic itself.
test("a failed admission release reports why, not just that it failed", () => {
  const source = fs.readFileSync("base44/functions/ownerScanDebugControl/entry.ts", "utf8");
  // persistExactRelease answers {ok, retryable, failureCode, state} -- there is
  // no .status and no .body, so the coordinator sanitizer reported status 0 and
  // an empty error for every release outcome.
  assert.match(source, /function sanitizeReleaseResult/);
  assert.match(source, /failure_code: cleanText\(result\?\.failureCode, 120\)/);
  assert.match(source, /retryable: result\?\.retryable === true/);
  // Two sites remain after the duplicate replay branches collapsed into one
  // helper: the helper itself, and the separate non-replay terminal path.
  assert.equal((source.match(/release: sanitizeReleaseResult\(release\)/g) || []).length, 2);
  assert.doesNotMatch(source, /release: sanitizeCoordinatorResult\(release\)/);
  assert.match(source, /function sanitizeCoordinatorResult/, "coordinator sanitization must remain");
});

test("the coordinator deadline covers the response body, not just the fetch", () => {
  const source = fs.readFileSync("base44/functions/ownerScanDebugControl/entry.ts", "utf8");
  const call = source.match(/const controller = new AbortController\(\);[\s\S]*?return \{ ok: response\.ok/)[0];
  // A coordinator that answers headers and then stalls its body would hold the
  // request with no deadline at all.
  const bodyRead = call.indexOf("await response.json()");
  const clears = [...call.matchAll(/clearTimeout\(timeout\)/g)].map((m) => m.index);
  assert.ok(bodyRead > 0, "the body read must still be present");
  assert.ok(clears.length >= 2, "the timer must be cleared on both the failure and the body path");
  assert.ok(
    clears.some((index) => index > bodyRead),
    "the deadline must still be armed while the body is read",
  );
  assert.match(call, /\} finally \{\n\s*clearTimeout\(timeout\);/);
  // The controller must be created outside the try, or the failure path cannot
  // clear it. Measured against the whole file: the slice above begins at the
  // controller, so an ordering check inside it would always hold.
  const controllerAt = source.indexOf("const controller = new AbortController();");
  const fetchTryAt = source.indexOf("try {", controllerAt === -1 ? 0 : controllerAt - 200);
  assert.ok(controllerAt > 0, "the controller declaration must exist");
  assert.ok(
    controllerAt < source.indexOf("response = await fetch("),
    "the controller must be created before the fetch",
  );
  assert.ok(controllerAt < fetchTryAt, "the controller must outlive the fetch try block");
});

test("both terminal replay branches answer through one path", () => {
  const source = fs.readFileSync("base44/functions/ownerScanDebugControl/entry.ts", "utf8");
  // Word-anchored: a renamed helper would leave the two call sites dangling
  // while a prefix match still "passed".
  assert.match(source, /async function terminalReplayResponse\(\{/);
  // Two byte-identical blocks drift; one helper called twice cannot.
  assert.equal((source.match(/return await terminalReplayResponse\(\{/g) || []).length, 2);
  assert.equal((source.match(/replayed: true,/g) || []).length, 1);
});
