import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { webcrypto } from "node:crypto";
import { buildAuthoritySnapshot, buildPersistedAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authorityRows.js";
import { authoritySnapshotFromRows } from "../../base44/functions/getCustomerScanResultV8/projection.js";
import { createAuthoritySeal, verifyAuthoritySeal } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySeal.js";

const OWNER = "owner-stage3-v7";
const SCAN = "scan-stage3-v7-durable";
const PROJECT = "project-stage3-v7";
const HELPER = "tests/helpers/emitRescanIdentityCompletion.py";
const identityFields = ["repair_identity_version", "repair_fingerprint", "repair_identity_state", "repair_identity_stable", "repair_surface", "remediation_family"];

function python(mode, input) {
  const result = spawnSync("python", [HELPER, mode], {
    encoding: "utf8",
    input: input === undefined ? undefined : JSON.stringify(input),
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

async function roundTrip(mode) {
  const emitted = python(mode);
  const { envelope, secret } = emitted;
  const signed = { version: envelope.version, identity: envelope.identity, scan: envelope.scan, review: envelope.review };
  assert.equal(await verifyAuthoritySeal(signed, secret, envelope.proof, webcrypto), true);
  const snapshot = buildAuthoritySnapshot({
    scan: envelope.scan, review: envelope.review,
    identity: { scan_id: SCAN, project_id: PROJECT, normalized_domain: "example.com" },
    userId: OWNER, now: "2026-09-23T09:00:00.000Z", identityVersion: emitted.identity_version,
  });
  const proof = await createAuthoritySeal(snapshot, secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, { fixListId: "identity-transport-fixture", ownerUserId: OWNER, proof });
  // JSON round trip models stored transport, not shared in-memory object identity.
  const data = JSON.parse(JSON.stringify({
    run: { ...rows.scanRun, id: SCAN, project_id: PROJECT },
    fixList: { ...rows.fixList, id: "identity-transport-fixture" },
    fixItems: rows.fixItems.map((item, index) => ({ ...item, id: `row-${index}` })),
    userId: OWNER,
  }));
  const restored = authoritySnapshotFromRows(data);
  assert.deepEqual(buildPersistedAuthoritySnapshot(data), snapshot);
  assert.deepEqual(restored, snapshot);
  assert.equal(await verifyAuthoritySeal(restored, secret, proof, webcrypto), true);
  return { emitted, snapshot, restored, data, proof, secret };
}

function compare(previous, current = []) {
  return python("compare", {
    previous, current,
    pages: previous.affected_pages.map((url) => ({ url, status_code: 200, content_type: "text/html", indexable: true })),
  });
}

for (const mode of ["stable", "provisional"]) {
  test(`${mode} technical identity survives signed Python producer, V8 rows and authenticated reload`, async () => {
    const { emitted, restored } = await roundTrip(mode);
    assert.ok(restored.recommendations.length > 0);
    for (const repair of restored.recommendations) {
      const producer = emitted.envelope.review.canonical_repairs.find((item) => item.fix_id === repair.fix_id);
      assert.ok(producer);
      assert.equal(repair.repair_identity_stable, mode === "stable");
      assert.equal(repair.repair_fingerprint, producer.repair_fingerprint);
      assert.equal(repair.repair_surface, producer.repair_identity.repair_surface);
      assert.equal(repair.remediation_family, producer.repair_identity.remediation_family);
      assert.equal(repair.repair_identity_state, producer.repair_identity.state);
    }
  });
}

test("stable reloaded repair remains comparable despite a changed finding identifier", async () => {
  const { restored } = await roundTrip("stable");
  const prior = restored.recommendations[0];
  const current = { ...prior, fix_id: "different-finding-id" };
  assert.equal(compare(prior, [current]).state, "still_detected");
});

test("provisional reloaded repair never becomes verified fixed from absence or fingerprint continuity", async () => {
  const { restored } = await roundTrip("provisional");
  for (const prior of restored.recommendations) {
    assert.equal(compare(prior).state, "could_not_verify");
    assert.equal(compare(prior, [{ ...prior, fix_id: "different-finding-id" }]).state, "could_not_verify");
  }
});

test("altering persisted technical identity invalidates the existing V8 seal", async () => {
  const { data, proof, secret } = await roundTrip("stable");
  for (const field of identityFields) {
    const changed = structuredClone(data);
    changed.fixItems[0][field] = field === "repair_identity_stable" ? false : "tampered-identity";
    const restored = authoritySnapshotFromRows(changed);
    assert.equal(await verifyAuthoritySeal(restored, secret, proof, webcrypto), false, field);
  }
});
