import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync("src/lib/scanRuns.js", "utf8");

function readerFor(result) {
  const calls = [];
  const base44 = {
    auth: { me: async () => ({ id: "owner_test" }) },
    functions: {
      invoke: async (name, body) => {
        calls.push({ name, body });
        return { data: result };
      },
    },
  };
  const runnable = source.replace(/^import[\s\S]*?;\n/gm, "").replace(/^export\s+/gm, "");
  const read = new Function("base44", "clearCustomerAuthBoundary", `${runnable}\nreturn getScanRunWithFixList;`)(base44, () => {});
  return { read, calls };
}

function limitedResponse(overrides = {}) {
  return {
    success: true,
    access: "full",
    authority_verified: false,
    result_integrity_verified: true,
    run: { id: "scan_test", project_id: "project_test", status: "limited", release_gate_eligible: false, score_is_provisional: true },
    fixList: { id: "list_test", project_id: "project_test", scan_run_id: "scan_test", is_authoritative: false },
    fixItems: [{ id: "fix_test", project_id: "project_test", scan_run_id: "scan_test", fix_list_id: "list_test", issue_title: "Check this page", page_count: 0 }],
    ...overrides,
  };
}

test("saved results use the active identity-compatible reader", async () => {
  const { read, calls } = readerFor(limitedResponse());
  await read("scan_test");
  assert.deepEqual(calls, [{ name: "getCustomerScanResultV8", body: { scan_id: "scan_test" } }]);
});

test("a server-verified limited result keeps its integrity marker and findings without becoming authoritative", async () => {
  const { read } = readerFor(limitedResponse());
  const bundle = await read("scan_test");
  assert.equal(bundle.ok, true);
  assert.equal(bundle.result_integrity_verified, true);
  assert.equal(bundle.authority_verified, false);
  assert.equal(bundle.run.status, "limited");
  assert.equal(bundle.run.release_gate_eligible, false);
  assert.equal(bundle.run.score_is_provisional, true);
  assert.equal(bundle.fixList.is_authoritative, false);
  assert.equal(bundle.fixItems.length, 1);
});

test("missing or nonboolean integrity flags cannot verify a result", async () => {
  for (const marker of [undefined, null, false, "true", 1]) {
    const { read } = readerFor(limitedResponse({ result_integrity_verified: marker }));
    const bundle = await read("scan_test");
    assert.equal(bundle.result_integrity_verified, false);
  }
});

test("verified markers never bypass scan, project, list, or item identity checks", async () => {
  const cases = [
    { run: { id: "different_scan", project_id: "project_test", status: "limited" } },
    { fixList: { id: "list_test", project_id: "different_project", scan_run_id: "scan_test" } },
    { fixItems: [{ project_id: "project_test", scan_run_id: "different_scan", fix_list_id: "list_test" }] },
    { fixItems: [{ project_id: "project_test", scan_run_id: "scan_test", fix_list_id: "different_list" }] },
  ];
  for (const mismatch of cases) {
    const { read } = readerFor(limitedResponse(mismatch));
    const bundle = await read("scan_test");
    assert.equal(bundle.ok, false);
    assert.equal(bundle.kind, "authority_invalid");
    assert.equal(bundle.retryable, false);
    assert.equal(bundle.fixItems, undefined);
  }
});

test("failed limited and preview proofs clear protected content instead of becoming retryable reads", async () => {
  for (const error_code of ["limited_result_invalid", "result_preview_invalid"]) {
    const { read } = readerFor({ success: false, error_code });
    const bundle = await read("scan_test");
    assert.equal(bundle.ok, false);
    assert.equal(bundle.kind, "authority_invalid");
    assert.equal(bundle.retryable, false);
    assert.equal(bundle.fixItems, undefined);
  }
});
