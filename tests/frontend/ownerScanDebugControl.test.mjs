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
