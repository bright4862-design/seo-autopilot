import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const endpoint = readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
const page = readFileSync("src/pages/FixList.jsx", "utf8");
const row = readFileSync("src/components/fixlist/RecentScanRow.jsx", "utf8");

test("dashboard history is owner-wide and remains a safe summary projection", () => {
  assert.match(endpoint, /action === "list_all"/);
  assert.match(endpoint, /owner_user_id: cleanId\(user\.id\)/);
  assert.match(endpoint, /buildScanHistoryProjection\(rows\)/);
  assert.match(scanRuns, /export async function listAccountScanRuns/);
  assert.match(scanRuns, /action: "list_all"/);
  assert.match(page, /listAccountScanRuns\(20\)/);
  assert.doesNotMatch(page, /getActiveProject\(\)/);
});

test("deletion preserves the selected scan's project boundary", () => {
  assert.match(page, /handleDeleteScan\(projectId, scanId\)/);
  assert.match(page, /deleteScanRun\(projectId, scanId\)/);
  assert.match(row, /onDelete\(scan\.project_id, scan\.id\)/);
});
