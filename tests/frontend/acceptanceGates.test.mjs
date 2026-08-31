import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  assetSuffixes,
  evaluateScan,
  expectedFingerprint,
  groupCardMinAffected,
  isAccessLimited,
  isAssetUrl,
  summarizeMatrix,
} from "../../scripts/acceptance-gates.mjs";

// These gates decide whether a release ships, so a gate that passes a bad scan
// is worse than no gate at all. Each test drives the real evaluator against a
// bundle shaped like the rows persistDurableScanAuthority actually writes.
const FINGERPRINT = expectedFingerprint();

function passingScan(overrides = {}) {
  return {
    id: "scan_001",
    website_url: "https://www.ikessandwich.com/",
    status: "complete",
    fix_list_id: "fixlist_001",
    pages_crawled: 138,
    pages_found: 210,
    deno_fallback_used: false,
    python_review_fallback_used: false,
    advanced_scan_backend: "python_scanner_api",
    ai_review_backend: "python_review_api",
    beta_revision_fingerprint: FINGERPRINT,
    archetype_classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
    primary_archetype: "ecommerce",
    release_gate_eligible: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
    authority_proof: "a".repeat(64),
    authority_sealed_at: "2026-08-31T09:00:00Z",
    ...overrides,
  };
}

const bundle = (scanOverrides = {}, fixItems = []) => ({
  scanRun: passingScan(scanOverrides),
  fixList: { id: "fixlist_001" },
  fixItems,
});

test("a clean complete scan passes every gate", () => {
  const result = evaluateScan(bundle({}, [
    { fix_id: "f1", rule: "missing_meta_description", page_url: "https://x.test/a", affected_pages: ["https://x.test/a"] },
  ]), { expected: { archetype: "ecommerce" } });
  assert.equal(result.pass, true, JSON.stringify(result.gates, null, 2));
});

test("the Standard 150 cap is a gate, not a suggestion", () => {
  const over = evaluateScan(bundle({ pages_crawled: 151 }));
  assert.equal(over.gates.infrastructure.pass, false);
  assert.match(over.gates.infrastructure.failures.join(" "), /exceeds the Standard 150 cap/);
  assert.equal(evaluateScan(bundle({ pages_crawled: 150 })).gates.infrastructure.pass, true);
  // A scan that crawled nothing is not a pass by absence.
  assert.equal(evaluateScan(bundle({ pages_crawled: 0 })).gates.infrastructure.pass, false);
});

test("every fallback marker is checked, not just one", () => {
  for (const override of [
    { deno_fallback_used: true },
    { python_review_fallback_used: true },
    { advanced_scan_backend: "deno_scanner" },
    { ai_review_backend: "deno_review" },
  ]) {
    const result = evaluateScan(bundle(override));
    assert.equal(result.gates.infrastructure.pass, false, `${JSON.stringify(override)} must fail infrastructure`);
  }
});

test("a scan carrying the wrong release identity fails infrastructure and authority", () => {
  const result = evaluateScan(bundle({ beta_revision_fingerprint: "5d94e93c54a9efb6" }));
  assert.equal(result.gates.infrastructure.pass, false);
  assert.match(result.gates.infrastructure.failures.join(" "), /is not the frozen/);
  // Claiming eligibility under a mismatched fingerprint is the exact production
  // failure this release chased; it must fail authority independently.
  assert.equal(result.gates.authority.pass, false);
  assert.match(result.gates.authority.failures.join(" "), /does not match the freeze/);
});

test("a missing or malformed authority proof is not a complete scan", () => {
  assert.equal(evaluateScan(bundle({ authority_proof: "" })).gates.infrastructure.pass, false);
  assert.equal(evaluateScan(bundle({ authority_proof: "not-a-proof" })).gates.infrastructure.pass, false);
  assert.equal(evaluateScan(bundle({ authority_sealed_at: "" })).gates.infrastructure.pass, false);
});

test("a FixList the ScanRun does not point at is a persistence failure", () => {
  const mismatched = { scanRun: passingScan(), fixList: { id: "fixlist_other" }, fixItems: [] };
  assert.equal(evaluateScan(mismatched).gates.infrastructure.pass, false);
  assert.match(evaluateScan(mismatched).gates.infrastructure.failures.join(" "), /points at FixList/);
});

test("assets are never FixItems, on either the anchor or the affected list", () => {
  const suffixes = assetSuffixes();
  for (const asset of ["https://x.test/logo.png", "https://x.test/app.js", "https://x.test/brief.pdf", "https://x.test/f.woff2"]) {
    assert.equal(isAssetUrl(asset, suffixes), true, `${asset} must read as an asset`);
  }
  for (const page of ["https://x.test/products", "https://x.test/", "https://x.test/a/b"]) {
    assert.equal(isAssetUrl(page, suffixes), false, `${page} must read as a page`);
  }
  // A query string must not disguise an asset, and a trailing slash must not either.
  assert.equal(isAssetUrl("https://x.test/logo.png?v=2", suffixes), true);
  assert.equal(isAssetUrl("https://x.test/logo.png/", suffixes), true);

  // Anchor and affected list are checked independently: a card anchored on an
  // asset while naming real pages is still a card about a file, not a page.
  const anchorOnly = evaluateScan(bundle({}, [
    { fix_id: "f1", rule: "image_alt", page_url: "https://x.test/logo.png", affected_pages: ["https://x.test/gallery"] },
  ]));
  assert.equal(anchorOnly.gates.evidence.pass, false, "an asset anchor alone must fail");
  assert.match(anchorOnly.gates.evidence.failures.join(" "), /anchored on an asset URL/);

  const listedOnly = evaluateScan(bundle({}, [
    { fix_id: "f2", rule: "image_alt", page_url: "https://x.test/gallery", affected_pages: ["https://x.test/gallery", "https://x.test/logo.png"] },
  ]));
  assert.equal(listedOnly.gates.evidence.pass, false, "an asset in the affected list alone must fail");
  assert.match(listedOnly.gates.evidence.failures.join(" "), /names 1 asset URL/);
});

test("a page card a grouped card already covers is a duplicate", () => {
  const min = groupCardMinAffected();
  const group = {
    fix_id: "group",
    rule: "redirect_destination_noindex",
    page_url: "https://x.test/menu/a",
    affected_pages: Array.from({ length: min + 2 }, (_, i) => `https://x.test/menu/${i}`),
  };
  const duplicate = {
    fix_id: "dupe",
    rule: "redirect_destination_noindex",
    page_url: "https://x.test/menu/1",
    affected_pages: ["https://x.test/menu/1"],
  };
  const result = evaluateScan(bundle({}, [group, duplicate]));
  assert.equal(result.gates.evidence.pass, false);
  assert.match(result.gates.evidence.failures.join(" "), /grouped card already covers/);

  // A row naming a page the group does not cover is a real outlier and survives.
  const outlier = { ...duplicate, fix_id: "outlier", page_url: "https://x.test/other", affected_pages: ["https://x.test/other"] };
  assert.equal(evaluateScan(bundle({}, [group, outlier])).gates.evidence.pass, true);

  // A different rule over the same pages is a different problem, not a duplicate.
  const otherRule = { ...duplicate, fix_id: "other_rule", rule: "missing_title" };
  assert.equal(evaluateScan(bundle({}, [group, otherRule])).gates.evidence.pass, true);
});

test("a stated affected-page count must match the URLs shown", () => {
  const lying = evaluateScan(bundle({}, [
    { fix_id: "f1", rule: "r", page_url: "https://x.test/a", affected_pages: ["https://x.test/a"], page_count: 40 },
  ]));
  assert.equal(lying.gates.evidence.pass, false);
  assert.match(lying.gates.evidence.failures.join(" "), /claims 40 affected pages but lists 1/);

  // A deliberately truncated list declares itself, and is not held to the count.
  const truncated = evaluateScan(bundle({}, [
    { fix_id: "f1", rule: "r", page_url: "https://x.test/a", affected_pages: ["https://x.test/a"], page_count: 40, affected_pages_complete: false },
  ]));
  assert.equal(truncated.gates.evidence.pass, true);
});

test("an access-limited scan is excluded from accuracy but must stay provisional", () => {
  const limited = passingScan({
    status: "limited",
    release_gate_eligible: false,
    score_is_provisional: true,
    primary_archetype: "",
  });
  assert.equal(isAccessLimited(limited), true);
  const result = evaluateScan({ scanRun: limited, fixList: { id: "fixlist_001" }, fixItems: [] }, {
    expected: { archetype: "ecommerce" },
  });
  assert.equal(result.gates.classification.excluded, true, "a blocked site must not count against the classifier");
  assert.equal(result.gates.classification.pass, true);
  assert.equal(result.gates.authority.pass, true);

  // But a limited scan claiming authority, or not marking itself provisional, fails.
  const overclaiming = { ...limited, release_gate_eligible: true };
  assert.equal(evaluateScan({ scanRun: overclaiming, fixList: { id: "fixlist_001" }, fixItems: [] }).gates.authority.pass, false);

  // The dangerous shape is a scan that completed but whose evidence was
  // blocked: status alone would wave it through, so the limitation itself has
  // to be what refuses eligibility.
  const completeButBlocked = passingScan({
    status: "complete",
    review_confidence_state: "blocked_access_needs_verification",
    release_gate_eligible: true,
    score_is_provisional: true,
  });
  assert.equal(isAccessLimited(completeButBlocked), true);
  const blockedResult = evaluateScan({ scanRun: completeButBlocked, fixList: { id: "fixlist_001" }, fixItems: [] });
  assert.equal(blockedResult.gates.authority.pass, false, "a complete-but-blocked scan must not claim authority");
  assert.match(blockedResult.gates.authority.failures.join(" "), /access-limited scan claims release-gate eligibility/);
  const notProvisional = { ...limited, score_is_provisional: false };
  assert.equal(evaluateScan({ scanRun: notProvisional, fixList: { id: "fixlist_001" }, fixItems: [] }).gates.authority.pass, false);
});

test("a wrong archetype fails classification only when the scan was conclusive", () => {
  const wrong = evaluateScan(bundle({ primary_archetype: "publisher" }), { expected: { archetype: "ecommerce" } });
  assert.equal(wrong.gates.classification.pass, false);
  assert.match(wrong.gates.classification.failures.join(" "), /is not the expected ecommerce/);
  // With no expectation declared, classification cannot fail on the archetype.
  assert.equal(evaluateScan(bundle({ primary_archetype: "publisher" })).gates.classification.pass, true);
});

test("the matrix summary keeps infrastructure and classification apart", () => {
  const results = [
    evaluateScan(bundle({ id: "s1" }, []), { site: "ike", expected: { archetype: "ecommerce" } }),
    evaluateScan(bundle({ id: "s2", primary_archetype: "publisher" }), { site: "wpbeginner", expected: { archetype: "ecommerce" } }),
    evaluateScan({
      scanRun: passingScan({ id: "s3", status: "limited", release_gate_eligible: false, score_is_provisional: true }),
      fixList: { id: "fixlist_001" },
      fixItems: [],
    }, { site: "shopify", expected: { archetype: "saas" } }),
  ];
  const summary = summarizeMatrix(results);

  // All three are infrastructurally sound; only two are conclusive, and one of
  // those is misclassified. Folding the blocked site into either number would
  // misreport both.
  assert.equal(summary.total, 3);
  assert.equal(summary.infrastructurePassed, 3);
  assert.equal(summary.conclusive, 2);
  assert.equal(summary.classificationPassed, 1);
  assert.equal(summary.classificationRate, 0.5);
  assert.deepEqual(summary.blocked, ["shopify"]);
  assert.equal(summary.betaGatesMet, false, "50% classification is below the 85% gate");
});

test("the beta gates are the stated thresholds, and every zero-tolerance rule holds", () => {
  const clean = Array.from({ length: 10 }, (_, i) =>
    evaluateScan(bundle({ id: `s${i}` }), { site: `site${i}`, expected: { archetype: "ecommerce" } }));
  assert.equal(summarizeMatrix(clean).betaGatesMet, true);

  // One infrastructure failure in ten is exactly 90% and still passes.
  const nine = [...clean.slice(0, 9), evaluateScan(bundle({ id: "bad", pages_crawled: 400 }), { site: "bad", expected: { archetype: "ecommerce" } })];
  assert.equal(summarizeMatrix(nine).infrastructureRate, 0.9);
  assert.equal(summarizeMatrix(nine).betaGatesMet, true);
  // Two is 80% and fails.
  const eight = [...clean.slice(0, 8),
    evaluateScan(bundle({ id: "b1", pages_crawled: 400 }), { site: "b1", expected: { archetype: "ecommerce" } }),
    evaluateScan(bundle({ id: "b2", pages_crawled: 400 }), { site: "b2", expected: { archetype: "ecommerce" } })];
  assert.equal(summarizeMatrix(eight).betaGatesMet, false);

  // A single asset FixItem or duplicate card sinks the release regardless of rates.
  const withAsset = [...clean.slice(0, 9), evaluateScan(bundle({ id: "a" }, [
    { fix_id: "f", rule: "image_alt", page_url: "https://x.test/l.png", affected_pages: ["https://x.test/l.png"] },
  ]), { site: "asset", expected: { archetype: "ecommerce" } })];
  const assetSummary = summarizeMatrix(withAsset);
  assert.equal(assetSummary.assetFindings, 1);
  assert.equal(assetSummary.betaGatesMet, false, "zero asset FixItems is zero-tolerance");

  const min = groupCardMinAffected();
  const grouped = {
    fix_id: "group",
    rule: "redirect_destination_noindex",
    page_url: "https://x.test/m/0",
    affected_pages: Array.from({ length: min + 1 }, (_, i) => `https://x.test/m/${i}`),
  };
  const withDuplicate = [...clean.slice(0, 9), evaluateScan(bundle({ id: "d" }, [
    grouped,
    { fix_id: "dupe", rule: "redirect_destination_noindex", page_url: "https://x.test/m/1", affected_pages: ["https://x.test/m/1"] },
  ]), { site: "dupe", expected: { archetype: "ecommerce" } })];
  const duplicateSummary = summarizeMatrix(withDuplicate);
  assert.equal(duplicateSummary.duplicateCards, 1);
  assert.equal(duplicateSummary.assetFindings, 0, "this case must be isolated to duplicates");
  assert.equal(duplicateSummary.betaGatesMet, false, "zero duplicate cards is zero-tolerance");
});

test("the thresholds come from the scanner, not a second copy here", () => {
  // A restated threshold would drift from the filter that actually runs, and
  // the gate would then measure something the product does not do.
  const gates = fs.readFileSync("scripts/acceptance-gates.mjs", "utf8");
  assert.match(gates, /scanner-api\/app\/artifact_filter\.py/);
  assert.match(gates, /scanner-api\/app\/repair_dedup\.py/);
  assert.match(gates, /data\/beta-crawler-revision\.json/);
  assert.equal(groupCardMinAffected(), 3);
  assert.ok(assetSuffixes().includes(".png") && assetSuffixes().includes(".woff2"));
  assert.match(expectedFingerprint(), /^[0-9a-f]{16}$/);
});
