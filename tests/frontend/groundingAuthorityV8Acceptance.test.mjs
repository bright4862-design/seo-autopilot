import assert from "node:assert/strict";
import test from "node:test";
import { createHash, webcrypto } from "node:crypto";
import { spawnSync } from "node:child_process";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authorityRows.js";
import { authoritySnapshotFromRows } from "../../base44/functions/getCustomerScanResultV8/projection.js";
import {
  createAuthoritySeal,
  stableSerialize,
  verifyAuthoritySeal,
} from "../../base44/functions/persistDurableScanAuthorityV8/authoritySeal.js";

const OWNER = "owner-stage3-v7";
const PROJECT = "project-stage3-v7";

function producerBridge(input) {
  const result = spawnSync("python", ["tests/helpers/scanComparisonAuthorityBridge.py"], {
    encoding: "utf8",
    input: JSON.stringify(input),
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function groundingBridge(input) {
  const result = spawnSync("python", ["tests/helpers/groundingAuthorityBridge.py"], {
    encoding: "utf8",
    input: JSON.stringify(input),
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

async function persistedV8Authority() {
  const emitted = producerBridge({
    action: "emit",
    scan_id: "grounding-v8-authority",
    mode: "stable",
  });
  const { envelope, secret } = emitted;
  const producerPayload = {
    version: envelope.version,
    identity: envelope.identity,
    scan: envelope.scan,
    review: envelope.review,
  };
  assert.equal(
    await verifyAuthoritySeal(producerPayload, secret, envelope.proof, webcrypto),
    true,
  );

  const snapshot = buildAuthoritySnapshot({
    scan: envelope.scan,
    review: envelope.review,
    identity: {
      scan_id: "grounding-v8-authority",
      project_id: PROJECT,
      normalized_domain: "example.com",
    },
    userId: OWNER,
    now: "2026-09-24T13:50:00.000Z",
    identityVersion: emitted.identity_version,
  });
  const proof = await createAuthoritySeal(snapshot, secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "list-grounding-v8-authority",
    ownerUserId: OWNER,
    proof,
  });
  const persisted = JSON.parse(JSON.stringify({
    run: {
      ...rows.scanRun,
      id: "grounding-v8-authority",
      project_id: PROJECT,
    },
    fixList: {
      ...rows.fixList,
      id: "list-grounding-v8-authority",
    },
    fixItems: rows.fixItems.map((item, index) => ({
      ...item,
      id: `grounding-v8-authority-${index}`,
    })),
    userId: OWNER,
  }));

  const restored = authoritySnapshotFromRows(persisted);
  assert.deepEqual(restored, snapshot);
  assert.equal(await verifyAuthoritySeal(restored, secret, proof, webcrypto), true);
  return { snapshot: restored, proof, secret };
}

test("real persisted V8 authority bytes produce one authenticated Grounding EvidenceSet", async () => {
  const authority = await persistedV8Authority();
  const before = structuredClone(authority.snapshot);
  const result = groundingBridge({
    snapshot: authority.snapshot,
    proof: authority.proof,
    signing_key: authority.secret,
  });

  assert.equal(result.ok, true, result.error);
  assert.equal(result.adapter_version, "grounding_v8_authority_adapter_v1");
  assert.equal(result.evidence.version, "ai_evidence_set_v1");
  assert.equal(result.evidence.scan_origin, "https://example.com");
  assert.equal(result.evidence.numeric_values["$.health_score"], authority.snapshot.scan.health_score);
  assert.equal(result.evidence.state_values["$.status"], "complete");
  assert.equal(result.evidence.state_values["$.release_gate_eligible"], true);
  assert.equal(Object.hasOwn(result.evidence.state_values, "$.authority_verified"), false);
  assert.ok(result.evidence.fix_refs.length > 0);
  assert.ok(result.evidence.url_members.includes("https://example.com/products/a"));
  assert.ok(result.evidence.url_members.includes("https://example.com/products/b"));
  assert.equal(result.evidence.live_urls.includes("https://example.com/products/a"), false);

  const nodeAuthoritySha = createHash("sha256")
    .update(stableSerialize(authority.snapshot))
    .digest("hex");
  assert.equal(result.authority_sha256, nodeAuthoritySha);
  assert.deepEqual(authority.snapshot, before);
});

test("tampering after V8 sealing cannot enter Grounding", async () => {
  const authority = await persistedV8Authority();
  const tampered = structuredClone(authority.snapshot);
  tampered.scan.health_score = Number(tampered.scan.health_score) + 1;

  const result = groundingBridge({
    snapshot: tampered,
    proof: authority.proof,
    signing_key: authority.secret,
  });
  assert.equal(result.ok, false);
  assert.equal(result.error, "sealed_l2_authentication_failed");
});

test("a freshly signed unknown authority version is still rejected", async () => {
  const authority = await persistedV8Authority();
  const unknown = structuredClone(authority.snapshot);
  unknown.version = "standard_review_snapshot_hmac_future_v1";
  const proof = await createAuthoritySeal(unknown, authority.secret, webcrypto);

  const result = groundingBridge({
    snapshot: unknown,
    proof,
    signing_key: authority.secret,
  });
  assert.equal(result.ok, false);
  assert.equal(result.error, "sealed_l2_authentication_failed");
});

test("a signed non-authoritative V8 state cannot be projected into Grounding", async () => {
  const authority = await persistedV8Authority();
  const nonAuthoritative = structuredClone(authority.snapshot);
  nonAuthoritative.scan.release_gate_eligible = false;
  const proof = await createAuthoritySeal(nonAuthoritative, authority.secret, webcrypto);

  const result = groundingBridge({
    snapshot: nonAuthoritative,
    proof,
    signing_key: authority.secret,
  });
  assert.equal(result.ok, false);
  assert.equal(result.error, "v8_grounding_projection_unavailable");
});
