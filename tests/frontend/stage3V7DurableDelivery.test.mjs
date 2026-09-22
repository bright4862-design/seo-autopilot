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
import { prepareCustomerFixes } from "../../src/lib/fixRanking.js";
import { buildRepairWorkSurfacePresentation } from "../../src/lib/repairWorkSurfacePresentation.js";
import { buildScanHandoff } from "../../src/lib/scanHandoff.js";

const PUBLISHED_AUTHORITY_VERSION = "standard_review_snapshot_hmac_identity_v1";
const STAGE3_DELIVERY_VERSION = "stage3_v7_delivery_v1";
const SCAN_ID = "scan-stage3-v7-durable";
const PROJECT_ID = "project-stage3-v7";
const OWNER_ID = "owner-stage3-v7";
const SEALED_AT = "2026-09-21T10:15:00.000Z";

function runPythonFixture(path) {
  const result = spawnSync("python", [path], {
    cwd: process.cwd(),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, `Python signed-completion fixture failed to execute (${path}):\n${result.stderr}`);
  return JSON.parse(result.stdout);
}

function signedPythonCompletion() {
  return runPythonFixture("tests/helpers/emitStage3SignedCompletion.py");
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

test("V7 customer projection restores canonical action order when a sealed Stage-3 selection was factor-ranked", async () => {
  const emitted = runPythonFixture("tests/helpers/emitStage3RankedCompletion.py");
  const { envelope } = emitted;
  const snapshot = buildAuthoritySnapshot({
    scan: envelope.scan,
    review: envelope.review,
    identity: {
      scan_id: emitted.scan_id,
      project_id: emitted.project_id,
      normalized_domain: "example.com",
    },
    userId: emitted.owner_id,
    now: SEALED_AT,
    identityVersion: emitted.identity_version,
  });
  const proof = await createAuthoritySeal(snapshot, emitted.secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fix-stage3-order-recovery",
    ownerUserId: emitted.owner_id,
    proof,
  });
  const reordered = {
    run: { ...rows.scanRun, id: emitted.scan_id, project_id: emitted.project_id },
    fixList: { ...rows.fixList, id: "fix-stage3-order-recovery" },
    fixItems: rows.fixItems.map((item, index) => ({ ...item, id: `order-recovery-${index + 1}` })),
    userId: emitted.owner_id,
  };
  const delivery = reordered.run.health_score_explanation.stage3_delivery.delivery;
  const selectedIds = [...delivery.displayed_fix_ids];
  assert.ok(selectedIds.length > 1);
  delivery.displayed_fix_ids = [...selectedIds].reverse();

  const customer = buildCustomerProjection({ ...reordered, fullAccess: true, authorityVerified: true });
  const ranks = customer.fixItems.map((item) => item.canonical_action_rank);
  assert.deepEqual(ranks, [...ranks].sort((left, right) => left - right));
  assert.deepEqual(
    new Set(customer.fixItems.map((item) => item.fix_id)),
    new Set(selectedIds),
    "Stage-3 decides membership; canonical action rank decides customer order",
  );

  const prepared = prepareCustomerFixes(customer.fixItems);
  const workSurface = buildRepairWorkSurfacePresentation({
    snapshotItems: prepared,
    visibleItems: prepared,
  });
  assert.equal(workSurface.presentation.unsupported, false);
  assert.equal(workSurface.presentation.canonical, true);
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


test("B19-B23 exact-scan authority survives when B22/B24 delivery sources are legitimately absent", async () => {
  const emitted = signedPythonCompletion();
  const review = structuredClone(emitted.envelope.review);
  assert.equal(review.stage3_authority_claim?.version, "stage3_authority_claim_v1");
  delete review.stage3_private_preview_source;
  delete review.stage3_handoff_v2_source;

  const snapshot = buildAuthoritySnapshot(authorityOptions({ ...emitted.envelope, review }, emitted));
  assert.equal(snapshot.version, PUBLISHED_AUTHORITY_VERSION);
  assert.equal(snapshot.scan.health_score_explanation.stage3_delivery.authority_claim.scan_id, SCAN_ID);
  assert.equal(snapshot.scan.health_score_explanation.stage3_delivery.private_preview_source, undefined);
  assert.equal(snapshot.scan.health_score_explanation.stage3_delivery.handoff_v2_source, undefined);
  assert.equal(snapshot.scan.health_score, review.stage3_health_score_decision.adjusted_health_score);

  const proof = await createAuthoritySeal(snapshot, emitted.secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, { fixListId: "fix-authority-only", ownerUserId: OWNER_ID, proof });
  const data = {
    run: { ...rows.scanRun, id: SCAN_ID, project_id: PROJECT_ID },
    fixList: { ...rows.fixList, id: "fix-authority-only" },
    fixItems: rows.fixItems.map((item, index) => ({ ...item, id: "authority-only-" + index })),
    userId: OWNER_ID,
  };
  const customer = buildCustomerProjection({ ...data, fullAccess: true, authorityVerified: true });
  assert.deepEqual(customer.run.stage3_health_score_decision, review.stage3_health_score_decision);
  assert.equal(customer.run.stage3_handoff_v2, undefined);
  assert.ok(customer.fixItems.every((item) => item.stage3_priority_factors?.version));
  assert.ok(customer.fixItems.every((item) => item.stage3_counts));

  const previewPayload = buildCustomerPreviewPayload({
    ...data,
    ownerUserId: OWNER_ID,
    fullAuthorityProof: proof,
  });
  assert.deepEqual(previewPayload.fixItems, [], "no signed B22 source means no unpaid findings are exposed");
});

test("B22 preview preserves the exact signed finding order instead of re-sorting by legacy rank", async () => {
  const emitted = runPythonFixture("tests/helpers/emitStage3RankedCompletion.py");
  const envelope = emitted.envelope;
  const snapshot = buildAuthoritySnapshot({
    scan: envelope.scan,
    review: envelope.review,
    identity: {
      scan_id: emitted.scan_id,
      project_id: emitted.project_id,
      normalized_domain: "example.com",
    },
    userId: emitted.owner_id,
    now: SEALED_AT,
    identityVersion: emitted.identity_version,
  });
  const proof = await createAuthoritySeal(snapshot, emitted.secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fix-preview-order",
    ownerUserId: emitted.owner_id,
    proof,
  });
  assert.ok(rows.fixItems.length >= 2);
  const run = { ...rows.scanRun, id: emitted.scan_id, project_id: emitted.project_id };
  const first = rows.fixItems[0].fix_id;
  const second = rows.fixItems[1].fix_id;
  run.health_score_explanation = structuredClone(run.health_score_explanation);
  run.health_score_explanation.stage3_delivery.private_preview_source.findings = [
    { rule_id: second, title: "Second", impact: 5, evidence_summary: null },
    { rule_id: first, title: "First", impact: 4, evidence_summary: null },
  ];
  const fixItems = rows.fixItems.map((item, index) => ({
    ...item,
    id: "preview-order-" + index,
    canonical_action_rank: index + 1,
    action_priority_score: 100 - index,
  }));
  const payload = buildCustomerPreviewPayload({
    run,
    fixList: { ...rows.fixList, id: "fix-preview-order" },
    fixItems,
    ownerUserId: emitted.owner_id,
    fullAuthorityProof: proof,
  });
  assert.deepEqual(payload.fixItems.map((item) => item.fix_id), [second, first]);
});

test("B24 a claimed but malformed Stage3 v2 handoff fails closed instead of silently exporting historical v1", async () => {
  const { data } = await liveWriterRows();
  const customer = buildCustomerProjection({ ...data, fullAccess: true, authorityVerified: true });
  const malformed = structuredClone(customer.run);
  malformed.stage3_handoff_v2 = { handoff_version: "fixlist_handoff_v2", scan: { scan_id: malformed.id } };
  assert.throws(
    () => buildScanHandoff({ scanRecord: malformed, cards: [], healthScore: malformed.health_score }),
    /Stage3 handoff/i,
  );
});

test("B19/B21 >36 candidates rank before truncation and preserve known zero versus unknown through signed V7 customer delivery", async () => {
  const emitted = runPythonFixture("tests/helpers/emitStage3RankedCompletion.py");
  const { envelope } = emitted;
  const signed = {
    version: envelope.version,
    identity: envelope.identity,
    scan: envelope.scan,
    review: envelope.review,
  };
  assert.equal(await verifyAuthoritySeal(signed, emitted.secret, envelope.proof, webcrypto), true);

  const delivery = envelope.review.stage3_delivery;
  assert.equal(delivery.eligible_candidate_count, 40);
  assert.equal(delivery.displayed_candidate_count, 36);
  assert.equal(delivery.presentation_truncated, true);
  assert.equal(delivery.presentation_omitted_count, 4);
  assert.equal(delivery.displayed_fix_ids.length, 36);
  assert.equal(delivery.displayed_fix_ids[0], "zz-soft404");

  const repairs = new Map(envelope.review.canonical_repairs.map((fix) => [fix.fix_id, fix]));
  const zero = repairs.get("zero-reach")?.stage3_priority_factors;
  const unknown = repairs.get("unknown-reach")?.stage3_priority_factors;
  assert.equal(zero?.reach, 0);
  assert.equal(zero?.priority_factor_score, 0);
  assert.ok(Number.isInteger(zero?.reach_observed_indexable_family) && zero.reach_observed_indexable_family > 0);
  assert.equal(unknown?.reach, null);
  assert.equal(unknown?.reach_observed_indexable_family, null);
  assert.equal(unknown?.priority_factor_score, null);

  const options = {
    scan: envelope.scan,
    review: envelope.review,
    identity: {
      scan_id: emitted.scan_id,
      project_id: emitted.project_id,
      normalized_domain: "example.com",
    },
    userId: emitted.owner_id,
    now: SEALED_AT,
    identityVersion: emitted.identity_version,
  };
  const snapshot = buildAuthoritySnapshot(options);
  assert.equal(snapshot.version, PUBLISHED_AUTHORITY_VERSION);
  const proof = await createAuthoritySeal(snapshot, emitted.secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fix-stage3-v7-ranked",
    ownerUserId: emitted.owner_id,
    proof,
  });
  const data = {
    run: { ...rows.scanRun, id: emitted.scan_id, project_id: emitted.project_id },
    fixList: { ...rows.fixList, id: "fix-stage3-v7-ranked" },
    fixItems: rows.fixItems.map((item, index) => ({ ...item, id: `ranked-fix-row-${index + 1}` })),
    userId: emitted.owner_id,
  };
  const rebuilt = authoritySnapshotFromRows(data);
  assert.equal(await verifyAuthoritySeal(rebuilt, emitted.secret, proof, webcrypto), true);

  const persistedUnknown = data.fixItems.find((item) => item.fix_id === "unknown-reach")?.raw_finding?.stage3_delivery?.priority_factors;
  const persistedZero = data.fixItems.find((item) => item.fix_id === "zero-reach")?.raw_finding?.stage3_delivery?.priority_factors;
  assert.equal(persistedUnknown?.reach, null);
  assert.equal(persistedUnknown?.priority_factor_score, null);
  assert.equal(persistedZero?.reach, 0);
  assert.equal(persistedZero?.priority_factor_score, 0);

  const customer = buildCustomerProjection({ ...data, fullAccess: true, authorityVerified: true });
  assert.deepEqual(customer.fixItems.map((item) => item.fix_id), delivery.displayed_fix_ids);
  assert.equal(customer.fixItems.length, 36);
  assert.equal(customer.fixItems[0].fix_id, "zz-soft404");
  const cards = buildRepairCards(customer.fixItems);
  assert.equal(cards.length, 36);
  assert.equal(cards[0].priorityFactors.impact, 5);

  const exported = buildScanHandoff({ scanRecord: customer.run, cards, healthScore: customer.run.health_score });
  assert.deepEqual(exported, envelope.review.stage3_handoff_v2_source);
  assert.equal(exported.fix_count, 40);

  const previewPayload = buildCustomerPreviewPayload({
    ...data,
    ownerUserId: emitted.owner_id,
    fullAuthorityProof: proof,
  });
  assert.deepEqual(
    previewPayload.fixItems.map((item) => item.fix_id),
    envelope.review.stage3_private_preview_source.findings.map((finding) => finding.rule_id),
  );
});
