import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { webcrypto, createHash } from "node:crypto";
import { buildAuthoritySnapshot, buildPersistedAuthoritySnapshot, firstFailedAuthorityPredicate } from "../../base44/functions/persistDurableScanAuthorityV6/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV6/authorityRows.js";
import { createAuthoritySeal, stableSerialize, verifyAuthoritySeal } from "../../base44/functions/persistDurableScanAuthorityV6/authoritySeal.js";
import { authoritySnapshotFromRows, buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV6/projection.js";
import { authoritySnapshotFromRows as grokSnapshot } from "../../base44/functions/grokChat/authoritySnapshot.js";
import { buildCustomerPreviewPayload, createCustomerPreviewProof, verifyCustomerPreviewProof } from "../../base44/functions/persistDurableScanAuthorityV6/customerPreviewSeal.js";

const IDENTITY = "evidence_url_identity_v2_published_route";
const SEAL = "standard_review_snapshot_hmac_identity_v1";
const COVERAGE = "repair_coverage_v5_published_route_identity";
const INVARIANT = "repair_invariant_v2_published_route_identity";
const secret = "geo-test-secret";
const geo = JSON.parse(readFileSync("tests/fixtures/geo/runtime.json", "utf8"));

function finding(urls = ["/x", "/x/", "/X"], overrides = {}) {
  return {
    fix_id: "metadata", rule: "missing_meta_description", category: "meta_description",
    issue_title: "Add descriptions", priority: "medium", page_scope: "family",
    page_template_family: "product_page", page_url: urls[0], affected_pages: urls,
    source_pages: urls, page_count: urls.length, family_breakdown: { product_page: urls.length },
    representative_pages_by_family: { product_page: urls[0] }, affected_pages_complete: true,
    evidence_url_identity_version: IDENTITY, repair_coverage_version: COVERAGE,
    ...overrides,
  };
}
function snapshotFor(fixes = [finding()]) {
  return buildAuthoritySnapshot({
    scan: { ...geo.scan, website_url: "https://example.com/", requested_origin: "https://example.com", pages_found: 3, pages_crawled: 3 },
    review: { geo_readiness: geo.failures, health_score: 93, recommendations: fixes },
    identity: { scan_id: "s", project_id: "p", normalized_domain: "example.com" },
    userId: "u", now: "2026-09-18T12:00:00.000Z", identityVersion: IDENTITY,
  });
}
async function stored(fixes) {
  const snapshot = snapshotFor(fixes);
  assert.equal(snapshot.version, SEAL);
  const proof = await createAuthoritySeal(snapshot, secret, webcrypto);
  const rows = authorityRowsFromSnapshot(snapshot, { fixListId: "f", ownerUserId: "u", proof });
  return { snapshot, proof, run: { ...rows.scanRun, id: "s", project_id: "p" },
    fixList: { ...rows.fixList, id: "f" }, fixItems: rows.fixItems.map((item, i) => ({ ...item, id: `row${i}` })), userId: "u" };
}

test("published route counts survive actual writer rows, writer readback, customer and Grok HMACs", async () => {
  const data = await stored();
  for (const snapshot of [buildPersistedAuthoritySnapshot(data), authoritySnapshotFromRows(data), grokSnapshot({ ...data, scan: data.run })]) {
    assert.deepEqual(snapshot, data.snapshot);
    assert.equal(await verifyAuthoritySeal(snapshot, secret, data.proof, webcrypto), true);
  }
  const [fix] = buildCustomerProjection({ ...data, fullAccess: true, authorityVerified: true }).fixItems;
  assert.equal(fix.page_count, 3);
  assert.deepEqual(fix.affected_pages, ["/x", "/x/", "/X"]);
  assert.deepEqual(fix.family_breakdown, { product_page: 3 });
  assert.equal(fix.evidence_url_identity_version, IDENTITY);
  assert.equal(fix.repair_coverage_version, COVERAGE);
  assert.equal(fix.repair_invariant_version, INVARIANT);
});
test("new authority suppresses only exact covered published URLs", () => {
  const variants = ["/x/", "/X", "/a%2Fb", "/a/b", "/q?a=1&b=2", "/q?b=2&a=1", "https://foreign.example/x"];
  const fixes = [finding(["/x", "/other"], { fix_id: "aggregate" }), ...variants.map((url, i) => finding([url], { fix_id: `single${i}`, page_scope: "page" })),
    finding(["https://example.com/x"], { fix_id: "covered", page_scope: "page" })];
  const snapshot = snapshotFor(fixes);
  assert.equal(snapshot.recommendations.length, variants.length + 1);
  assert.equal(snapshot.recommendations.some(fix => fix.fix_id === "covered"), false);
});
test("new authority rejects missing marker and refuses to sign dropped persisted evidence", async () => {
  assert.throws(() => snapshotFor([finding(undefined, { evidence_url_identity_version: undefined })]), /identity|published/);
  const data = await stored();
  delete data.fixItems[0].raw_finding.published_evidence;
  assert.throws(() => buildPersistedAuthoritySnapshot(data), /identity|published/);
});
test("customer completion does not invalidate the new report's chat authority", async () => {
  const data = await stored();
  data.fixItems[0].user_status = "done";
  for (const snapshot of [buildPersistedAuthoritySnapshot(data), authoritySnapshotFromRows(data), grokSnapshot({ ...data, scan: data.run })]) {
    assert.equal(await verifyAuthoritySeal(snapshot, secret, data.proof, webcrypto), true);
    assert.equal(snapshot.recommendations[0].user_status, "open");
  }
  const customer = buildCustomerProjection({ ...data, fullAccess: true, authorityVerified: true });
  assert.equal(customer.fixItems[0].user_status, "done");
});
test("persisted writer rejects unknown seals instead of upgrading them to the current contract", async () => {
  const data = await stored();
  for (const version of ["unknown", "standard_review_snapshot_hmac_identity_v2", ""]) {
    data.run.authority_seal_version = version;
    assert.throws(() => buildPersistedAuthoritySnapshot(data), /unsupported.*seal/i);
  }
});
test("malformed published canonical evidence returns a predicate rejection rather than throwing", () => {
  const review = { repair_contract_version: "repair_contract_v2_shadow_calibrated",
    repair_snapshot_contract_version: "repair_contract_v2_shadow_calibrated",
    repair_snapshot_contract_complete: true, repair_priority_model_version: "repair_priority_v2_technical_severity",
    canonical_repairs: [finding(undefined, { evidence_url_identity_version: undefined })] };
  assert.equal(firstFailedAuthorityPredicate({ website_url: "https://example.com" }, review, { identityVersion: IDENTITY }), "scanner_version");
});
test("new HMAC rejects route, reserved escape, count, partition and marker mutations", async () => {
  const data = await stored([finding(["/a%2Fb", "/x/", "/X"])]);
  const mutations = [
    row => { row.affected_pages[1] = "/x"; },
    row => { row.affected_pages[0] = "/a/b"; },
    row => { row.page_count = 2; },
    row => { row.family_breakdown.product_page = 2; },
    row => { row.raw_finding.published_evidence.evidence_url_identity_version = "unknown"; },
    row => { row.raw_finding.published_evidence.repair_coverage_version = "unknown"; },
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(data); mutate(changed.fixItems[0]);
    let rejected = false;
    try { rejected = !await verifyAuthoritySeal(authoritySnapshotFromRows(changed), secret, data.proof, webcrypto); }
    catch (error) { assert.match(error.message, /identity|published/); rejected = true; }
    assert.equal(rejected, true);
  }
});
test("published preview preserves GEO, two-fix limit and exact example without hidden evidence", async () => {
  const data = await stored([finding(["/x/"], { fix_id: "a", page_scope: "page" }),
    finding(["/X"], { fix_id: "b", page_scope: "page" }), finding(["/hidden"], { fix_id: "c", page_scope: "page" })]);
  const payload = buildCustomerPreviewPayload({ ...data, ownerUserId: "u", fullAuthorityProof: data.proof });
  assert.equal(payload.fixItems.length, 2);
  assert.equal(payload.fixItems[0].preview_example_page, "/x/");
  assert.equal(payload.run.geo_readiness.assessment_status, "assessed");
  const encoded = JSON.stringify(payload);
  for (const hidden of ["/hidden", "published_evidence", "representative_pages_by_family", '"observations"']) assert.equal(encoded.includes(hidden), false, hidden);
  const proof = await createCustomerPreviewProof(payload, secret, webcrypto);
  assert.equal(await verifyCustomerPreviewProof(payload, secret, proof, webcrypto), true);
});
test("frozen GEO signature and preview survive new-marker injection without upgrading historical semantics", async () => {
  const fixture = JSON.parse(readFileSync("tests/fixtures/geo/historical-geo-seal.json", "utf8"));
  const data = fixture.data;
  assert.equal(createHash("sha256").update(stableSerialize(fixture.snapshot)).digest("hex"), fixture.serialized_sha256);
  for (const injected of [IDENTITY, "unknown"]) {
    data.fixItems[0].evidence_url_identity_version = injected;
    data.fixItems[0].raw_finding.published_evidence = { evidence_url_identity_version: injected, repair_coverage_version: COVERAGE, repair_invariant_version: INVARIANT };
    for (const snapshot of [buildPersistedAuthoritySnapshot(data), authoritySnapshotFromRows(data), grokSnapshot({ ...data, scan: data.run })]) {
      assert.deepEqual(snapshot, fixture.snapshot);
      assert.equal(await verifyAuthoritySeal(snapshot, secret, fixture.proof, webcrypto), true);
    }
    const result = buildCustomerProjection({ ...data, fullAccess: true, authorityVerified: true });
    assert.equal(result.fixItems[0].evidence_url_identity_version, undefined);
    assert.equal(result.fixItems[0].raw_finding.published_evidence, undefined);
  }
  assert.equal(await verifyCustomerPreviewProof(fixture.preview.payload, secret, fixture.preview.proof, webcrypto), true);
});
