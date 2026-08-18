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
  const source = fs.readFileSync("base44/functions/ownerScanDebugControl/index.ts", "utf8");
  assert.match(source, /bright4862@gmail\.com/);
  assert.match(source, /6a498da58ef5cec1f5cd4486/);
  assert.match(source, /role[^\n]+admin/i);
  assert.match(source, /attempt_count/);
  assert.match(source, /owner_manual_kill/);
  assert.match(source, /\/release/);
  assert.match(source, /\/status/);
  assert.match(source, /release_gate_eligible:\s*false/);
});

test("FixList surfaces owner-only Debug scan and Force stop scan controls", () => {
  const source = fs.readFileSync("src/pages/FixList.jsx", "utf8");
  assert.match(source, /Debug scan/);
  assert.match(source, /Force stop scan/);
  assert.match(source, /isOwnerScanDebugUser/);
});
