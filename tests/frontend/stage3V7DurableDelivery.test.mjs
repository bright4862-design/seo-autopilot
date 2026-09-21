import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { webcrypto } from "node:crypto";
import {
  buildAuthoritySnapshot,
  buildPersistedAuthoritySnapshot,
} from "../../base44/functions/persistDurableScanAuthorityV7/authoritySnapshot.js";
import { buildAuthoritySnapshot as buildStage1LegacyAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV7/authoritySnapshotStage1Legacy.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV7/authorityRows.js";
import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
} from "../../base44/functions/getCustomerScanResultV7/projection.js";
import { authoritySnapshotFromRows as grokSnapshot } from "../../base44/functions/grokChat/authoritySnapshot.js";
import {
  buildCustomerPreviewPayload,
  createCustomerPreviewProof,
  verifyCustomerPreviewProof,
} from "../../base44/functions/persistDurableScanAuthorityV7/customerPreviewSeal.js";
import { createAuthoritySeal, verifyAuthoritySeal } from "../../base44/functions/persistDurableScanAuthorityV7/authoritySeal.js";
import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import { buildScanHandoff } from "../../src/lib/scanHandoff.js";

const PUBLISHED_AUTHORITY_VERSION = "standard_review_snapshot_hmac_identity_v1";
const STAGE3_DELIVERY_VERSION = "stage3_v7_delivery_v1";
const SCAN_ID = "scan-stage3-v7-durable";
const PROJECT_ID = "project-stage3-v7";
const OWNER_ID = "owner-stage3-v7";
const SEALED_AT = "2026-09-21T10:15:00.000Z";

function signedPythonCompletion() {
  const result = spawnSync("python", ["tests/helpers/emitStage3SignedCompletion.py"], {
    cwd: process.cwd(),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, `Python signed-completion fixture failed to execute:\n${result.stderr}`);
  return JSON.parse(result.stdout);
}

function authorityOptions(envelope, emitted) {
  return {
    scan: envelope.scan,
    review: envelope.review,
    identity: {
      scan_id: SCAN_ID,
      project_id: PROJECT_ID,
      normalized_domain: "example.com",
    },
    userId: OWNER_ID,
    now: SEALED_AT,
    identityVersion: emitted.identity_version,
  };
}

async function liveWriterRows() {
  const emitted = signedPythonCompletion();
  const { envelope } = emitted;
  const signed = {
    version: envelope.version,
    identity: envelope.identity,
    scan: envelope.scan,
    review: envelope.review,
  };
  assert.equal(
    await verifyAuthoritySeal(signed, emitted.secret, envelope.proof, webcrypto),
    true,
    "the real Python completion HMAC must verify before V7 transport is assessed",
  );
  assert.equal(envelope.review.stage3_delivery.version, "stage3_delivery_v1_rank_before_truncate");
  assert.equal(envelope.review.stage3_private_preview_source.version, "stage3_preview_source_v1_verified_evidence");
  assert.equal(envelope.review.stage3_health_score_decision.version, "stage3_health_score_caps_v1_verified_root_cause");
  assert.equal(envelope.review.stage3_handoff_v2_source.handoff_version, "fixlist_handoff_v2");
  assert.ok(envelope.review.canonical_repairs.every((fix) => fix.stage3_priority_factors?.version));
  assert.ok(envelope.review.canonical_repairs.every((fix) => fix.stage3_counts));

  const snapshot = buildAuthoritySnapshot(authorityOptions(envelope, emitted));
  const proof = await createAuthoritySeal(snapshot, emitted.secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, { fixListId: "fix-stage3-v7", ownerUserId: OWNER_ID, proof });
  const data = {
    run: { ...rows.scanRun, id: SCAN_ID, project_id: PROJECT_ID },
    fixList: { ...rows.fixList, id: "fix-stage3-v7" },
    fixItems: rows.fixItems.map((item, index) => ({ ...item, id: `fix-row-${index + 1}` })),
    userId: OWNER_ID,
  };
  return { emitted, envelope, snapshot, proof, rows, data };
}

test("B19-B24 signed Python review extends the active published-route V7 HMAC and applies the stricter score ceiling", async () => {
  const { envelope, snapshot } = await liveWriterRows();
  const decision = envelope.review.stage3_health_score_decision;
  assert.equal(decision.existing_score_ceiling, 64);
  assert.equal(decision.root_cause_score_ceiling, 72);
  assert.equal(decision.effective_score_ceiling, 64);
  assert.equal(decision.adjusted_health_score, 64);

  assert.equal(snapshot.version, PUBLISHED_AUTHORITY_VERSION);
  assert.equal(snapshot.scan.health_score, 64);
  assert.equal(snapshot.fix_list.health_score, 64);
  assert.equal(snapshot.scan.health_score_explanation.stage3_delivery.version, STAGE3_DELIVERY_VERSION);
  assert.deepEqual(snapshot.scan.health_score_explanation.stage3_delivery.health_score_decision, decision);
});

test("B19/B21 per-fix factors and honest counts survive V7 rows and both authenticated reconstruction paths", async () => {
  const { envelope, snapshot, proof, data, emitted } = await liveWriterRows();
  const expectedById = new Map(envelope.review.canonical_repairs.map((fix) => [fix.fix_id, fix]));

  for (const row of data.fixItems) {
    const expected = expectedById.get(row.fix_id);
    assert.ok(expected, row.fix_id);
    assert.deepEqual(row.raw_finding.stage3_delivery.priority_factors, expected.stage3_priority_factors);
    assert.deepEqual(row.raw_finding.stage3_delivery.counts, expected.stage3_counts);
  }

  for (const [name, rebuilt] of [
    ["writer", buildPersistedAuthoritySnapshot(data)],
    ["customer", authoritySnapshotFromRows(data)],
    ["grok", grokSnapshot({ ...data, scan: data.run })],
  ]) {
    assert.deepEqual(rebuilt, snapshot, name);
    assert.equal(await verifyAuthoritySeal(rebuilt, emitted.secret, proof, webcrypto), true, name);
  }
});

test("B22/B23/B24 verified customer, preview, cards and export consume the authenticated Stage-3 result without exposing it when locked", async () => {
  const { envelope, proof, data, emitted } = await liveWriterRows();
  const customer = buildCustomerProjection({ ...data, fullAccess: true, authorityVerified: true });
  assert.equal(customer.run.health_score, envelope.review.stage3_health_score_decision.adjusted_health_score);
  assert.deepEqual(customer.run.stage3_health_score_decision, envelope.review.stage3_health_score_decision);
  assert.deepEqual(customer.run.stage3_handoff_v2, envelope.review.stage3_handoff_v2_source);
  assert.ok(customer.fixItems.every((item) => item.stage3_priority_factors?.version));
  assert.ok(customer.fixItems.every((item) => item.stage3_counts));

  const cards = buildRepairCards(customer.fixItems);
  assert.ok(cards.every((card) => card.priorityFactors?.version));
  assert.ok(cards.every((card) => card.stage3Counts));
  const exported = buildScanHandoff({ scanRecord: customer.run, cards, healthScore: customer.run.health_score });
  assert.deepEqual(exported, envelope.review.stage3_handoff_v2_source);

  const previewPayload = buildCustomerPreviewPayload({
    ...data,
    ownerUserId: OWNER_ID,
    fullAuthorityProof: proof,
  });
  const expectedPreviewIds = envelope.review.stage3_private_preview_source.findings.map((finding) => finding.rule_id);
  assert.deepEqual(previewPayload.fixItems.map((item) => item.fix_id), expectedPreviewIds);
  const previewProof = await createCustomerPreviewProof(previewPayload, emitted.secret, webcrypto);
  assert.equal(await verifyCustomerPreviewProof(previewPayload, emitted.secret, previewProof, webcrypto), true);

  const locked = buildCustomerProjection({ ...data, fullAccess: false, previewAccess: false, authorityVerified: true });
  assert.deepEqual(locked.fixItems, []);
  assert.equal(locked.run.stage3_handoff_v2, undefined);
  assert.equal(locked.run.stage3_health_score_decision, undefined);
});

test("B27 unsigned Stage-3 markers cannot upgrade an otherwise valid historical published-route authority row", async () => {
  const { emitted, envelope, snapshot } = await liveWriterRows();
  const legacySnapshot = buildStage1LegacyAuthoritySnapshot(authorityOptions(envelope, emitted));
  assert.equal(legacySnapshot.version, PUBLISHED_AUTHORITY_VERSION);
  assert.equal(legacySnapshot.scan.health_score_explanation?.stage3_delivery, undefined);
  const legacyProof = await createAuthoritySeal(legacySnapshot, emitted.secret, webcrypto);
  const legacyRows = authorityRowsFromSnapshot(legacySnapshot, {
    fixListId: "fix-stage3-v7-legacy",
    ownerUserId: OWNER_ID,
    proof: legacyProof,
  });
  const legacyData = {
    run: { ...legacyRows.scanRun, id: SCAN_ID, project_id: PROJECT_ID },
    fixList: { ...legacyRows.fixList, id: "fix-stage3-v7-legacy" },
    fixItems: legacyRows.fixItems.map((item, index) => ({ ...item, id: `legacy-fix-row-${index + 1}` })),
    userId: OWNER_ID,
  };
  const rebuiltLegacy = authoritySnapshotFromRows(legacyData);
  assert.deepEqual(rebuiltLegacy, legacySnapshot);
  assert.equal(await verifyAuthoritySeal(rebuiltLegacy, emitted.secret, legacyProof, webcrypto), true);

  const injected = structuredClone(legacyData);
  injected.run.health_score = snapshot.scan.health_score;
  injected.fixList.health_score = snapshot.fix_list.health_score;
  injected.run.health_score_explanation = structuredClone(snapshot.scan.health_score_explanation);
  const byId = new Map(snapshot.recommendations.map((fix) => [fix.fix_id, fix.raw_finding.stage3_delivery]));
  injected.fixItems = injected.fixItems.map((item) => ({
    ...item,
    raw_finding: {
      ...(item.raw_finding || {}),
      stage3_delivery: structuredClone(byId.get(item.fix_id)),
    },
  }));
  const injectedSnapshot = authoritySnapshotFromRows(injected);
  assert.equal(await verifyAuthoritySeal(injectedSnapshot, emitted.secret, legacyProof, webcrypto), false);
});
