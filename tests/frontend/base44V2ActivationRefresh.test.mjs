import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const EXPECTED = new Map([
  ["startStandardScanJobV2", "start-standard-v2-activation-refresh-20260907-v1"],
  ["durableScanWorkerControlV2", "durable-worker-v2-activation-refresh-20260907-v1"],
  ["persistDurableScanAuthorityV2", "durable-authority-v2-activation-refresh-20260907-v1"],
  ["persistLimitedScanResultV2", "limited-result-v2-activation-refresh-20260907-v1"],
  ["getCustomerScanResultV2", "customer-result-v2-activation-refresh-20260907-v1"],
  ["deleteCustomerScanDataV2", "delete-history-v2-activation-refresh-20260907-v1"],
]);

test("every release-sensitive V2 handler carries a fresh compile-cache activation marker", () => {
  for (const [name, marker] of EXPECTED) {
    const source = ["entry.ts", "index.ts"]
      .map((file) => {
        try { return readFileSync(`base44/functions/${name}/${file}`, "utf8"); }
        catch { return ""; }
      })
      .join("\n");
    assert.match(source, new RegExp(`BASE44_RUNTIME_ACTIVATION_ID = ["']${marker}["']`), name);
    assert.match(source, /runtime_activation_id:\s*BASE44_RUNTIME_ACTIVATION_ID/, name);
  }
});

test("V2 activation markers are distinct from their legacy route packages", () => {
  for (const [name, marker] of EXPECTED) {
    const legacy = name.replace(/V2$/, "");
    const source = readFileSync(`base44/functions/${legacy}/entry.ts`, "utf8");
    assert.doesNotMatch(source, new RegExp(marker), name);
  }
});
