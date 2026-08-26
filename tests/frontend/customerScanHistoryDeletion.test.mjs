import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const backend = readFileSync("base44/functions/deleteCustomerScanData/index.ts", "utf8");
const config = readFileSync("base44/functions/deleteCustomerScanData/function.jsonc", "utf8");
const frontend = readFileSync("src/lib/scanHistory.js", "utf8");

test("saved scan deletion is owner-verified and server-side", () => {
  assert.match(config, /"name"\s*:\s*"deleteCustomerScanData"/);
  assert.match(backend, /base44\.auth\.me\(\)/);
  assert.match(backend, /cleanId\(project\.owner_user_id\) !== cleanId\(user\.id\)/);
  assert.match(backend, /cleanId\(run\.owner_user_id\) !== cleanId\(userId\)/);
  assert.match(frontend, /base44\.functions\.invoke\(DELETE_FUNCTION/);
});

test("active scanner state is never deleted by history cleanup", () => {
  assert.match(backend, /ACTIVE_STATUSES = new Set\(\["queued", "crawling", "reviewing"\]\)/);
  assert.match(backend, /active_scan_protected/);
  assert.match(backend, /protected_active_scan_ids/);
  assert.doesNotMatch(backend, /entities\.ScanRun\.update/);
});

test("automatic pruning keeps the newest three and only deletes terminal history", () => {
  assert.match(backend, /const KEEP_NEWEST = 3/);
  assert.match(backend, /ordered\.slice\(0, KEEP_NEWEST\)/);
  assert.match(backend, /TERMINAL_STATUSES\.has\(status\)/);
  assert.match(frontend, /KEEP_NEWEST_SCANS = 3/);
});

test("authority rows are removed only after exact owner project and scan checks", () => {
  assert.match(backend, /cleanId\(item\?\.owner_user_id\) === cleanId\(userId\)/);
  assert.match(backend, /cleanId\(item\?\.project_id\) === cleanId\(projectId\)/);
  assert.match(backend, /cleanId\(item\?\.scan_run_id\) === cleanId\(scanId\)/);
  assert.match(backend, /await entities\.FixItem\.delete/);
  assert.match(backend, /await entities\.FixList\.delete/);
  assert.match(backend, /await entities\.ScanRun\.delete\(scanId\)/);
});

test("child read failures cannot be reinterpreted as empty data before parent deletion", () => {
  const deletionStart = backend.indexOf("async function deleteOwnedTerminalScan");
  const helperStart = backend.indexOf("async function requiredRows", deletionStart);
  assert.ok(deletionStart >= 0, "deleteOwnedTerminalScan is missing");
  assert.ok(helperStart > deletionStart, "requiredRows fail-closed helper is missing");
  const deletion = backend.slice(deletionStart, helperStart);

  assert.doesNotMatch(
    deletion,
    /\.filter\([\s\S]*?\)\.catch\(\(\)\s*=>\s*\[\]\)/,
    "a failed child read must never become an empty child set",
  );
  assert.match(deletion, /requiredRows\([\s\S]*?FixList\.filter/);
  assert.match(deletion, /requiredRows\([\s\S]*?FixItem\.filter/);
  assert.ok(
    deletion.lastIndexOf("requiredRows(") < deletion.indexOf("await entities.ScanRun.delete(scanId)"),
    "every required child read must complete before the parent ScanRun can be deleted",
  );
});

test("required child reads fail with a sanitized service error instead of deletion success", () => {
  const helper = backend.match(/async function requiredRows[\s\S]*?\n\}/)?.[0] || "";
  assert.ok(helper, "requiredRows fail-closed helper is missing");
  assert.match(helper, /throw new RequestProblem\(\s*503,/);
  assert.match(helper, /Saved scan history is temporarily unavailable/);
  assert.doesNotMatch(helper, /error\.(?:message|stack)|JSON\.stringify/);
});
