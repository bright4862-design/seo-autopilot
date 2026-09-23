import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function client(invoke, clear = () => {}) {
  const source = readFileSync("src/lib/scanRuns.js", "utf8")
    .replace(/^import[\s\S]*?;\n/gm, "")
    .replace(/^export\s+/gm, "");
  return new Function("base44", "clearCustomerAuthBoundary", `${source}\nreturn getScanComparison;`)(
    { auth: { me: async () => ({ id: "owner" }) }, functions: { invoke } }, clear,
  );
}

test("comparison sends only the exact current ID and takes its authority from the dedicated response", async () => {
  const comparison = { current_scan_id: "current", previous_scan_id: "prior" };
  const read = client(async (route, body) => {
    assert.equal(route, "getCustomerScanResultV8");
    assert.deepEqual(body, { action: "compare", scan_id: "current" });
    return { data: { success: true, scan_id: "current", comparison_verified: true, comparison } };
  });
  assert.deepEqual(await read("current"), {
    scan_id: "current", comparison_status: "ready", comparison_verified: true, comparison,
  });
});

test("ordinary scan authority, stale identities, errors and missing payloads never authenticate comparison", async () => {
  for (const result of [
    null,
    { success: true, scan_id: "current", authority_verified: true },
    { success: true, scan_id: "prior", comparison_verified: true, comparison: { current_scan_id: "current" } },
    { success: true, scan_id: "current", comparison_verified: true, comparison: { current_scan_id: "prior" } },
    { success: false, scan_id: "current", comparison_verified: true },
  ]) {
    assert.equal((await client(async () => ({ data: result }))("current")).comparison_status, "unavailable");
  }
  assert.equal((await client(async () => { throw new Error("unreachable"); })("current")).comparison_verified, false);
});

test("first scans can omit the panel, while unauthorized reads clear the customer boundary", async () => {
  const first = client(async () => ({ success: true, scan_id: "current", comparison_status: "no_previous_scan", comparison_verified: false }));
  assert.equal((await first("current")).comparison_status, "no_previous_scan");
  let cleared = 0;
  const unauthorized = client(async () => { throw { response: { status: 401 } }; }, () => cleared++);
  assert.equal((await unauthorized("current")).comparison_status, "unavailable");
  assert.equal(cleared, 1);
});
