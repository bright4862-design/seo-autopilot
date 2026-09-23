import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { webcrypto } from "node:crypto";
import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authorityRows.js";
import { authoritySnapshotFromRows } from "../../base44/functions/getCustomerScanResultV8/projection.js";
import { createAuthoritySeal, verifyAuthoritySeal } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySeal.js";
import { buildScanComparisonPanelModel } from "../../src/lib/scanComparisonPanelModel.js";

const OWNER = "owner-stage3-v7";
const PROJECT = "project-stage3-v7";
function bridge(input) {
  const result = spawnSync("python", ["tests/helpers/scanComparisonAuthorityBridge.py"], {
    encoding: "utf8", input: JSON.stringify(input),
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}
async function reload(scanId, time, mode) {
  const emitted = bridge({ action: "emit", scan_id: scanId, mode });
  const { envelope, secret } = emitted;
  const producerPayload = { version: envelope.version, identity: envelope.identity, scan: envelope.scan, review: envelope.review };
  assert.equal(await verifyAuthoritySeal(producerPayload, secret, envelope.proof, webcrypto), true);
  const snapshot = buildAuthoritySnapshot({
    scan: envelope.scan, review: envelope.review,
    identity: { scan_id: scanId, project_id: PROJECT, normalized_domain: "example.com" },
    userId: OWNER, now: time, identityVersion: emitted.identity_version,
  });
  const proof = await createAuthoritySeal(snapshot, secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, { fixListId: `list-${scanId}`, ownerUserId: OWNER, proof });
  const persisted = JSON.parse(JSON.stringify({
    run: { ...rows.scanRun, id: scanId, project_id: PROJECT },
    fixList: { ...rows.fixList, id: `list-${scanId}` },
    fixItems: rows.fixItems.map((item, i) => ({ ...item, id: `${scanId}-${i}` })), userId: OWNER,
  }));
  const restored = authoritySnapshotFromRows(persisted);
  assert.deepEqual(restored, snapshot);
  assert.equal(await verifyAuthoritySeal(restored, secret, proof, webcrypto), true);
  return { snapshot: restored, proof, secret, persisted };
}
async function pair(mode = "stable") {
  const previous = await reload("comparison-before", "2026-09-23T09:00:00.000Z", mode);
  const current = await reload("comparison-after", "2026-09-23T10:00:00.000Z", mode);
  const input = {
    previous_snapshot: previous.snapshot, previous_proof: previous.proof,
    current_snapshot: current.snapshot, current_proof: current.proof,
    expected_owner_user_id: OWNER, expected_project_id: PROJECT,
    expected_current_scan_id: "comparison-after", signing_key: current.secret,
  };
  const issued = bridge({ action: "issue", ...input, current_previous_scan_id: "comparison-before" });
  assert.equal(issued.ok, true, issued.error);
  return { input, lineage: issued.result, previous, current };
}

test("real V8 persisted snapshots and signed lineage reach the existing comparison panel model", async () => {
  const { input, lineage } = await pair();
  const before = structuredClone(input);
  const result = bridge({ action: "compare", ...input, lineage_artifact: lineage });
  assert.equal(result.ok, true, result.error);
  assert.equal(result.result.comparison.summary.still_detected, 1);
  assert.equal(result.result.comparison.summary.fixed, 0);
  assert.equal(result.result.current_pages_available, true);
  assert.equal(result.result.customer_projection_authorized, false);
  const panel = buildScanComparisonPanelModel(result.result.presentation);
  assert.equal(panel.state, "ready");
  assert.equal(panel.currentScanId, "comparison-after");
  assert.equal(panel.counts.still_detected, 1);
  assert.equal(panel.scoreDirectionClaimAllowed, false);
  assert.deepEqual(input, before);
});

test("provisional history survives reload without becoming verified continuity or fixed", async () => {
  const { input, lineage } = await pair("provisional");
  const result = bridge({ action: "compare", ...input, lineage_artifact: lineage });
  assert.equal(result.ok, true, result.error);
  assert.equal(result.result.comparison.summary.fixed, 0);
  assert.equal(result.result.comparison.summary.still_detected, 0);
  assert.equal(result.result.comparison.summary.could_not_verify, 1);
});

test("persisted previous_scan_id alone is not evidence of authenticated lineage", async () => {
  const { input, lineage, current } = await pair();
  current.persisted.run.previous_scan_id = "another-scan";
  const rebuilt = authoritySnapshotFromRows(current.persisted);
  assert.deepEqual(rebuilt, input.current_snapshot);
  assert.equal(await verifyAuthoritySeal(rebuilt, current.secret, current.proof, webcrypto), true);
  const forged = structuredClone(lineage);
  forged.previous_scan_id = "another-scan";
  assert.equal(bridge({ action: "compare", ...input, lineage_artifact: forged }).ok, false);
  assert.equal(bridge({ action: "compare", ...input, lineage_artifact: {} }).ok, false);
});

test("altering actual persisted identity invalidates snapshot authority before comparison", async () => {
  const { input, lineage, current } = await pair();
  current.persisted.fixItems[0].repair_surface = "invented-surface";
  const changed = authoritySnapshotFromRows(current.persisted);
  assert.equal(bridge({ action: "compare", ...input, current_snapshot: changed, lineage_artifact: lineage }).ok, false);
});
