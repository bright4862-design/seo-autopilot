import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { webcrypto } from "node:crypto";
import { buildAuthoritySnapshot, buildPersistedAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV9/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV9/authorityRows.js";
import { authoritySnapshotFromRows, buildCustomerProjection, createAuthoritySeal, verifyAuthoritySeal } from "../../base44/functions/getCustomerScanResultV9/projection.js";
import { buildRepairCard } from "../../src/lib/repairCardModel.js";

// Exercise the real Python canonical/Stage3 producer with four independent
// surfaces. Page importance deliberately disagrees with canonical action rank.
const fixture = spawnSync("python", ["-c", `
import runpy
fixture = runpy.run_path("tests/helpers/emitStage3RankedCompletion.py")
scope = fixture["main"].__globals__
original_apply = scope["apply_canonical_repair_contract"]
def four_repairs(review, scan, **kwargs):
    fixes = review["cleaned_fixes"][:4]
    pages = scan["crawled_pages"][:4]
    for index, (fix, page) in enumerate(zip(fixes, pages)):
        family = "first-fixes-family-" + str(index)
        fix["page_template_family"] = family
        fix["who_can_do_this"] = "developer"
        fix["difficulty"] = "easy"
        page["page_template_family"] = family
        page["importance_score"] = [0.1, 0.9, 0.5, 0.8][index]
    review["cleaned_fixes"] = fixes
    scan["crawled_pages"] = pages
    scan["pages_found"] = scan["pages_crawled"] = len(pages)
    return original_apply(review, scan, **kwargs)
scope["apply_canonical_repair_contract"] = four_repairs
fixture["main"]()
`], { cwd: process.cwd(), encoding: "utf8" });
assert.equal(fixture.status, 0, fixture.stderr || String(fixture.error));
const emitted = JSON.parse(fixture.stdout);
const NOW = "2026-11-11T12:00:00.000Z";

async function roundtrip({ editReview = () => {}, staged = true, historicalIds } = {}) {
  const envelope = structuredClone(emitted.envelope);
  if (staged) Object.assign(envelope.scan, { page_cap: 150, pipeline_mode: "staged", scan_mode: "standard_150" });
  editReview(envelope.review);
  // Test variations are signed with the fixture's test key before entering the
  // writer, just as the worker signs its complete review payload.
  const signed = { version: envelope.version, identity: envelope.identity, scan: envelope.scan, review: envelope.review };
  const sourceProof = await createAuthoritySeal(signed, emitted.secret, webcrypto);
  assert.equal(await verifyAuthoritySeal(signed, emitted.secret, sourceProof, webcrypto), true);
  const before = structuredClone(envelope);
  const snapshot = buildAuthoritySnapshot({
    scan: envelope.scan, review: envelope.review, identity: envelope.identity,
    userId: emitted.owner_id, now: NOW, identityVersion: emitted.identity_version,
  });
  assert.deepEqual(envelope, before);
  if (historicalIds) snapshot.fix_list.top_action_fix_ids = historicalIds;
  const proof = await createAuthoritySeal(snapshot, emitted.secret, webcrypto);
  const saved = authorityRowsFromSnapshot(snapshot, { fixListId: "first-fixes-list", ownerUserId: emitted.owner_id, proof });
  const rows = {
    run: { ...saved.scanRun, id: emitted.scan_id, project_id: emitted.project_id },
    fixList: { ...saved.fixList, id: "first-fixes-list" },
    fixItems: saved.fixItems.map((fix, index) => ({ ...fix, id: `first-fixes-row-${index}` })),
    userId: emitted.owner_id,
  };
  return { envelope, snapshot, rows, proof, customer: buildCustomerProjection({ ...rows, fullAccess: true, authorityVerified: true }) };
}

async function assertSealedRoundtrip({ snapshot, rows, proof }) {
  const before = structuredClone(rows);
  for (const rebuilt of [buildPersistedAuthoritySnapshot(rows), authoritySnapshotFromRows(rows)]) {
    assert.deepEqual(rebuilt.fix_list.top_action_fix_ids, snapshot.fix_list.top_action_fix_ids);
    assert.deepEqual(rebuilt, snapshot);
    assert.equal(await verifyAuthoritySeal(rebuilt, emitted.secret, proof, webcrypto), true);
  }
  assert.deepEqual(rows, before);
}

test("new V9 Stage3 shortlists use signed factor order and distinct signed roots after normalization", async () => {
  const result = await roundtrip();
  assert.deepEqual(result.envelope.review.canonical_repairs.map(fix => fix.fix_id), ["meta-00", "meta-01", "meta-02", "meta-03"]);
  assert.deepEqual(result.snapshot.fix_list.top_action_fix_ids, ["meta-01", "meta-03", "meta-02"]);
  assert.deepEqual(result.customer.top_fix_ids, ["meta-01", "meta-03", "meta-02"]);
  assert.deepEqual(result.snapshot.recommendations.map(fix => fix.canonical_action_rank), [1, 2, 3, 4]);
  for (const repair of result.envelope.review.canonical_repairs) {
    assert.deepEqual(result.rows.fixItems.find(fix => fix.fix_id === repair.fix_id).raw_finding.stage3_delivery.priority_factors, repair.stage3_priority_factors);
  }
  await assertSealedRoundtrip(result);
});

for (const alias of ["who_does_it", "implementation_owner", "raw_finding"]) {
  test(`new V9 Stage3 retains an owner assignment from ${alias} through sealing and customer cards`, async () => {
    const result = await roundtrip({ editReview(review) {
      const owner = review.canonical_repairs[0];
      delete owner.who_can_do_this;
      if (alias === "raw_finding") owner.raw_finding = { ...owner.raw_finding, implementation_owner: "site_owner" };
      else owner[alias] = "site_owner";
    } });
    assert.deepEqual(result.snapshot.fix_list.top_action_fix_ids, ["meta-01", "meta-03", "meta-00"]);
    assert.deepEqual(result.customer.top_fix_ids, result.snapshot.fix_list.top_action_fix_ids);
    assert.equal(buildRepairCard(result.customer.fixItems.find(fix => fix.fix_id === "meta-00")).who, "You");
    await assertSealedRoundtrip(result);
  });
}

for (const restriction of ["direct", "retained"]) test(`${restriction} developer-only evidence overrides owner labels in new V9 Stage3 selection and customer cards`, async () => {
  const result = await roundtrip({ editReview(review) {
    for (const repair of review.canonical_repairs) {
      repair.who_can_do_this = "you";
      if (restriction === "direct") repair.requires_developer = true;
      else repair.raw_finding = { ...repair.raw_finding, requires_developer: true };
    }
    if (restriction === "direct") review.canonical_repairs[0].requires_developer = false;
    else delete review.canonical_repairs[0].raw_finding.requires_developer;
  } });
  assert.deepEqual(result.customer.top_fix_ids, ["meta-01", "meta-03", "meta-00"]);
  for (const fix of result.customer.fixItems) {
    assert.equal(buildRepairCard(fix).who, fix.fix_id === "meta-00" ? "You" : "Developer");
  }
  await assertSealedRoundtrip(result);
});

for (const [label, staged, stage3] of [["pre-V9 Stage3", false, true], ["historical staged V9 Stage3", true, true], ["historical staged V9 legacy", true, false]]) {
  test(`${label} snapshots reconstruct their signed shortlist without applying the new selector`, async () => {
    // The former selector treated the easy specialist task as owner-doable and
    // used the shared rule fallback, so it signed only the first canonical row.
    const historicalIds = staged ? ["meta-00"] : ["meta-00", "meta-01", "meta-02"];
    const result = await roundtrip({ staged, historicalIds, editReview(review) {
      review.canonical_repairs[3].who_can_do_this = "you";
      if (!stage3) delete review.stage3_authority_claim;
    } });
    await assertSealedRoundtrip(result);
    assert.deepEqual(result.rows.fixList.top_action_fix_ids, historicalIds);
  });
}

test("V9 customer selection stays within signed Stage3 display eligibility", async () => {
  const result = await roundtrip({ editReview(review) {
    review.canonical_repairs[0].who_can_do_this = "you";
    Object.assign(review.stage3_delivery, {
      displayed_fix_ids: ["meta-01", "meta-02", "meta-03"], displayed_candidate_count: 3,
      presentation_omitted_count: 1, presentation_truncated: true,
    });
  } });
  assert.deepEqual(result.snapshot.fix_list.top_action_fix_ids, ["meta-01", "meta-03", "meta-00"]);
  assert.deepEqual(result.customer.top_fix_ids, ["meta-01", "meta-03", "meta-02"]);
  assert.deepEqual(result.customer.fixItems.map(fix => fix.fix_id), ["meta-01", "meta-02", "meta-03"]);
  const locked = buildCustomerProjection({ ...result.rows, fullAccess: false, previewAccess: false, authorityVerified: true });
  assert.deepEqual(locked.top_fix_ids ?? [], []);
  assert.deepEqual(locked.fixItems, []);
  await assertSealedRoundtrip(result);
});

test("altering the stored V9 shortlist breaks both reconstructed HMACs", async () => {
  const result = await roundtrip();
  const tampered = structuredClone(result.rows);
  tampered.fixList.top_action_fix_ids.reverse();
  for (const rebuilt of [buildPersistedAuthoritySnapshot(tampered), authoritySnapshotFromRows(tampered)]) {
    assert.equal(await verifyAuthoritySeal(rebuilt, emitted.secret, result.proof, webcrypto), false);
  }
});
