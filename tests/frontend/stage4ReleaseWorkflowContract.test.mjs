import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const publish = fs.readFileSync(".github/workflows/fixlist-base44-release-publish.yml", "utf8");
const cloud = fs.readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
const manifest = fs.readFileSync("scripts/base44_release_manifest.mjs", "utf8");

test("Base44 release is owner-only, main-only and exact-SHA confirmed", () => {
  assert.match(publish, /github\.actor == 'bright4862-design'/);
  assert.match(publish, /github\.ref == 'refs\/heads\/main'/);
  assert.match(publish, /test "\$\(git rev-parse HEAD\)" = "\$\{\{ github\.sha \}\}"/);
  assert.match(publish, /test "\$\(git rev-parse origin\/main\)" = "\$\{\{ github\.sha \}\}"/);
  assert.match(publish, /test "\$INPUT_CONFIRM" = "\$source_sha"/);
  assert.match(publish, /Authenticate Base44 owner with ephemeral device code/);
});

test("release package manifest declares exactly six V6 scanner runtime functions", () => {
  const block = manifest.match(/export const RELEASE_FUNCTIONS = \[([\s\S]*?)\];/);
  assert.ok(block);
  const all = [...block[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  const v6 = all.filter((name) => name.endsWith("V6"));
  assert.deepEqual(v6, [
    "startStandardScanJobV6",
    "durableScanWorkerControlV6",
    "persistDurableScanAuthorityV6",
    "persistLimitedScanResultV6",
    "getCustomerScanResultV6",
    "deleteCustomerScanDataV6",
  ]);
});

test("Cloud operator exposes guarded stage, promote, rollback and acceptance-only operations", () => {
  for (const operation of [
    "build-worker-candidate",
    "promote-worker",
    "rollback-worker",
    "barrier-status",
    "verify-zero-admission-obligations",
    "cutover-pause",
    "cutover-resume",
    "open-claim-barrier",
    "acceptance-only",
  ]) {
    assert.match(cloud, new RegExp(`- ${operation.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  }
  assert.match(cloud, /acceptance_total_claim_budget/);
  assert.match(cloud, /acceptance_per_owner_claim_budget/);
  assert.match(cloud, /test "\$\{\{ github\.ref \}\}" = "refs\/heads\/main"/);
  assert.match(cloud, /test "\$\(git rev-parse origin\/main\)" = "\$\{\{ github\.sha \}\}"/);
});
