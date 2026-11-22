import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const publish = fs.readFileSync(".github/workflows/fixlist-base44-release-publish.yml", "utf8");
const cloud = fs.readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
const manifest = fs.readFileSync("scripts/base44_release_manifest.mjs", "utf8");

const SCANNER_ROLES = [
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "getCustomerScanResult",
  "deleteCustomerScanData",
];

test("Base44 release is owner-only, main-only and exact-SHA confirmed", () => {
  assert.match(publish, /github\.actor == 'bright4862-design'/);
  assert.match(publish, /github\.ref == 'refs\/heads\/main'/);
  assert.match(publish, /test "\$\(git rev-parse HEAD\)" = "\$\{\{ github\.sha \}\}"/);
  assert.match(publish, /test "\$\(git rev-parse origin\/main\)" = "\$\{\{ github\.sha \}\}"/);
  assert.match(publish, /test "\$INPUT_CONFIRM" = "\$source_sha"/);
  assert.match(publish, /Authenticate Base44 owner with ephemeral device code/);
});

test("release package manifest declares all six scanner roles at one versioned route generation", () => {
  const block = manifest.match(/export const RELEASE_FUNCTIONS = \[([\s\S]*?)\];/);
  assert.ok(block);
  const all = [...block[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  const matches = [];
  for (const role of SCANNER_ROLES) {
    const candidates = all.filter((name) => new RegExp(`^${role}V\\d+$`).test(name));
    assert.equal(candidates.length, 1, `${role} must have one release function`);
    matches.push(candidates[0]);
  }
  const generations = new Set(matches.map((name) => name.match(/(V\d+)$/)?.[1]));
  assert.equal(generations.size, 1, "all six scanner release functions must use the same route generation");
});

test("Cloud operator exposes guarded staging and rollback; promotion requires owner-comment path", () => {
  for (const operation of [
    "build-worker-candidate",
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
  const choices = cloud.split("        options:\n", 2)[1]?.split("      revision:", 1)[0];
  assert.ok(choices, "workflow_dispatch operation choices must exist");
  assert.doesNotMatch(choices, /- promote-worker/, "manual dispatch must not offer promotion");
  assert.match(cloud, /Refusing direct promotion: use the guarded owner-comment release path/);
  assert.match(cloud, /- name: Verify candidate runtime release identity before promotion/);
  assert.match(cloud, /export OPERATION=promote-worker/);
  assert.match(cloud, /if ! OPERATION=verify-worker-runtime-revision/);
  assert.match(cloud, /acceptance_total_claim_budget/);
  assert.match(cloud, /acceptance_per_owner_claim_budget/);
  assert.match(cloud, /test "\$\{\{ github\.ref \}\}" = "refs\/heads\/main"/);
  assert.match(cloud, /test "\$\(git rev-parse origin\/main\)" = "\$\{\{ github\.sha \}\}"/);
});
