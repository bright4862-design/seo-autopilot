import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  HEALTH_SCORE_EXPLANATION_VERSION,
  healthScoreExplanation,
} from "../../src/lib/healthScoreExplanation.js";
import {
  REVIEW_ATTESTATION_VERSION,
  buildAuthoritySnapshot,
} from "../../base44/functions/persistDurableScanAuthorityV2/authoritySnapshot.js";
import {
  authoritySnapshotFromRows,
  buildCustomerProjection,
} from "../../base44/functions/getCustomerScanResultV2/projection.js";

/**
 * The score has to be able to account for itself.
 *
 * The page showed a number and a grade, and the number is the first thing an
 * owner argues with -- particularly a low one on a site whose only findings are
 * image descriptions. The scanner has always known where every point went;
 * none of it left the scanner.
 *
 * The reader's job is narrow: display what was persisted and refuse anything
 * that does not add up. It recomputes nothing, because a browser that can
 * derive the score can also disagree with it, and then the page is arguing
 * with itself in front of the customer.
 */

const SEALED = {
  version: HEALTH_SCORE_EXPLANATION_VERSION,
  starting_score: 100,
  final_score: 58,
  total_deduction: 42,
  deductions: [
    { category: "Search visibility", points: 24 },
    { category: "Site navigation", points: 12 },
    { category: "Page content", points: 6 },
  ],
  coverage_ceiling: 100,
  applied_ceiling: 100,
  ceiling_reason: "",
  floor_applied: false,
  verification_findings_excluded: true,
};

test("a sealed explanation is read back as it was written", () => {
  const view = healthScoreExplanation({ health_score: 58, health_score_explanation: SEALED });

  assert.equal(view.available, true);
  assert.equal(view.finalScore, 58);
  assert.equal(view.totalDeduction, 42);
  assert.deepEqual(view.deductions.map((row) => row.category), [
    "Search visibility", "Site navigation", "Page content",
  ]);
  assert.equal(view.verificationExcluded, true);
});

test("an explanation that disagrees with the stored score is refused whole", () => {
  // Showing a breakdown next to a score it does not add up to is worse than
  // showing nothing: the customer cannot tell which number is the real one,
  // and both are ours.
  const view = healthScoreExplanation({
    health_score: 71,
    health_score_explanation: { ...SEALED, final_score: 58 },
  });
  assert.equal(view.available, false);
  assert.deepEqual(view.deductions, []);
});

test("deductions that do not sum to their stated total are refused", () => {
  const view = healthScoreExplanation({
    health_score: 58,
    health_score_explanation: { ...SEALED, total_deduction: 40 },
  });
  assert.equal(view.available, false);
});

test("an unknown explanation version is not guessed at", () => {
  const view = healthScoreExplanation({
    health_score: 58,
    health_score_explanation: { ...SEALED, version: "health_score_explanation_v9_invented" },
  });
  assert.equal(view.available, false);
});

test("a category outside the recognised set is dropped, not printed", () => {
  // The category strings are written by the scanner and rendered verbatim. An
  // allowlist here is what stops a bucket key or a diagnostic string reaching
  // the page through a field nobody is watching.
  const view = healthScoreExplanation({
    health_score: 58,
    health_score_explanation: {
      ...SEALED,
      deductions: [
        { category: "Search visibility", points: 24 },
        { category: "technical_quality", points: 12 },
        { category: "Site navigation", points: 6 },
      ],
    },
  });
  // Dropping a row breaks the sum, and a breakdown missing points is not a
  // breakdown, so the whole thing is refused rather than silently shortened.
  assert.equal(view.available, false);
});

test("the reader shows at most four areas", () => {
  const five = ["Search visibility", "Site navigation", "Search appearance", "Page content", "Website setup"];
  const view = healthScoreExplanation({
    health_score: 50,
    health_score_explanation: {
      ...SEALED,
      final_score: 50,
      total_deduction: 50,
      deductions: five.map((category, index) => ({ category, points: 14 - index * 2 })),
    },
  });
  assert.equal(view.available, true);
  assert.equal(view.deductions.length, 4, "a fifth row adds nothing an owner would act on");
  assert.equal(view.remainingDeduction, 6, "the points not itemised are still accounted for");
});

test("an evidence ceiling is described as a limit of the scan, not a fault of the site", () => {
  for (const [reason, pattern] of [
    ["sample_size", /pages we checked|sample/i],
    ["blocked_access", /limited automated access|blocked/i],
    ["incomplete_evidence", /enough|evidence/i],
    ["no_pages_crawled", /no pages/i],
  ]) {
    const view = healthScoreExplanation({
      health_score: 45,
      health_score_explanation: { ...SEALED, final_score: 45, applied_ceiling: 45, ceiling_reason: reason },
    });
    assert.equal(view.available, true);
    assert.ok(view.ceilingNote, `${reason} has no customer note`);
    assert.match(view.ceilingNote, pattern);
    assert.doesNotMatch(view.ceilingNote, /_/, `${reason} leaked its key: ${view.ceilingNote}`);
  }
});

test("an unrecognised ceiling reason produces no claim about why", () => {
  const view = healthScoreExplanation({
    health_score: 45,
    health_score_explanation: { ...SEALED, final_score: 45, applied_ceiling: 45, ceiling_reason: "other" },
  });
  assert.equal(view.available, true);
  assert.equal(view.ceilingNote, "", "an unnamed limit is not described, only the score stands");
});

test("the floor is stated rather than left as broken arithmetic", () => {
  const view = healthScoreExplanation({
    health_score: 40,
    health_score_explanation: {
      ...SEALED, final_score: 40, total_deduction: 89, floor_applied: true,
      deductions: [{ category: "Search visibility", points: 45 }, { category: "Site navigation", points: 44 }],
    },
  });
  assert.equal(view.available, true);
  assert.ok(view.floorNote, "100 - 89 is 11, and the score says 40");
  assert.match(view.floorNote, /lowest/i);
});

test("an older record says so instead of having its score reverse-engineered", () => {
  const view = healthScoreExplanation({ health_score: 62 });
  assert.equal(view.available, false);
  assert.equal(view.legacy, true);
  assert.match(view.legacyNote, /older result/i);
  assert.deepEqual(view.deductions, []);
});

test("a record with no score at all is not legacy, it is unscored", () => {
  // These are two different things and they read differently: "we have no
  // breakdown for this old scan" versus "this scan could not be scored".
  const view = healthScoreExplanation({ health_score: null });
  assert.equal(view.available, false);
  assert.equal(view.legacy, false);
  assert.equal(view.legacyNote, "");
});

test("the reader never recomputes a score of its own", () => {
  const source = fs.readFileSync(new URL("../../src/lib/healthScoreExplanation.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, /100 - |penalt|severity|bucket_caps/i,
    "a browser that can derive the score can also disagree with it");
});

// ------------------------------------------------ it survives the seal chain --

const REVIEW = {
  health_score: 58,
  health_grade: "Needs work",
  scan_status: "complete",
  health_score_explanation: SEALED,
  recommendations: [],
};

test("the explanation is sealed with the result it explains", () => {
  // Outside the seal the displayed breakdown could be edited without breaking
  // the proof, which would make it a decoration rather than evidence.
  const snapshot = buildAuthoritySnapshot({
    scan: { scan_id: "s1", website_url: "https://x.com", pages_found: 40, pages_crawled: 40 },
    review: REVIEW,
    identity: { scan_id: "s1", project_id: "p1", normalized_domain: "x.com" },
    userId: "u1",
  });
  assert.deepEqual(snapshot.scan.health_score_explanation, SEALED);
  assert.equal(snapshot.scan.health_score, 58);
});

test("what gets sealed is the normalized shape, not whatever the review held", () => {
  // The seal covers exactly what the normalizer returns, and reconstruction
  // runs the same normalizer over the stored row. Sealing the raw object
  // instead would put whatever the review happened to carry inside the proof --
  // and a row that round-trips through storage will not reproduce it, so an
  // intact result reads as tampered. The fixture is deliberately untidy.
  const untidy = {
    ...SEALED,
    deductions: [
      { category: "Search visibility", points: 24, internal_rule: "canonical_target_noindex" },
      { category: "Site navigation", points: 12 },
      { category: "Page content", points: 6 },
      { category: "", points: 3 },
      { category: "Website setup", points: 0 },
    ],
    action_penalties: { canonical_target_noindex: 24 },
    ceiling_reason: null,
  };
  const snapshot = buildAuthoritySnapshot({
    scan: { scan_id: "s1", website_url: "https://x.com", pages_found: 40, pages_crawled: 40 },
    review: { ...REVIEW, health_score_explanation: untidy },
    identity: { scan_id: "s1", project_id: "p1", normalized_domain: "x.com" },
    userId: "u1",
  });

  const sealedExplanation = snapshot.scan.health_score_explanation;
  assert.ok(!("action_penalties" in sealedExplanation), "an internal field reached the seal");
  assert.equal(sealedExplanation.ceiling_reason, "");
  assert.deepEqual(sealedExplanation.deductions, [
    { category: "Search visibility", points: 24 },
    { category: "Site navigation", points: 12 },
    { category: "Page content", points: 6 },
  ], "rows with no category or no points are not part of the sealed shape");
  for (const row of sealedExplanation.deductions) {
    assert.deepEqual(Object.keys(row), ["category", "points"]);
  }
});

test("the sealed row rebuilds to the same snapshot it was signed as", () => {
  // Reconstruction has to be byte-identical or an intact result reads as
  // tampered. This is the assertion that catches a field added to one side.
  const snapshot = buildAuthoritySnapshot({
    scan: { scan_id: "s1", website_url: "https://x.com", pages_found: 40, pages_crawled: 40 },
    review: REVIEW,
    identity: { scan_id: "s1", project_id: "p1", normalized_domain: "x.com" },
    userId: "u1",
  });

  const rebuilt = authoritySnapshotFromRows({
    run: {
      id: "s1",
      project_id: "p1",
      normalized_domain: "x.com",
      website_url: "https://x.com",
      authority_seal_version: REVIEW_ATTESTATION_VERSION,
      authority_sealed_at: snapshot.sealed_at,
      status: "complete",
      release_gate_eligible: true,
      pages_found: 40,
      pages_crawled: 40,
      scan_status: "complete",
      health_score: 58,
      health_grade: "Needs work",
      health_score_explanation: SEALED,
      completed_at: snapshot.sealed_at,
    },
    fixList: { id: "fl1" },
    fixItems: [],
    userId: "u1",
  });

  assert.deepEqual(
    rebuilt.scan.health_score_explanation,
    snapshot.scan.health_score_explanation,
    "the sealed explanation does not survive reconstruction",
  );
});

test("a row sealed under an older version gains no field its seal did not cover", () => {
  const rebuilt = authoritySnapshotFromRows({
    run: {
      id: "s1",
      authority_seal_version: "standard_review_snapshot_hmac_v4_focused_scope",
      health_score: 58,
      health_score_explanation: SEALED,
    },
    fixList: { id: "fl1" },
    fixItems: [],
    userId: "u1",
  });
  assert.ok(!("health_score_explanation" in rebuilt.scan),
    "a v4 row must rebuild exactly as v4 or its stored proof stops verifying");
});

test("the customer projection carries the explanation, bounded", () => {
  const projected = buildCustomerProjection({
    run: {
      id: "s1", scan_id: "s1", website_url: "https://x.com", status: "complete",
      pages_found: 40, pages_crawled: 40, health_score: 58,
      health_score_explanation: SEALED,
    },
    fixList: { id: "fl1" },
    fixItems: [],
    fullAccess: true,
    authorityVerified: true,
  });
  assert.deepEqual(projected.run.health_score_explanation, SEALED);

  // And the page reads it from exactly that shape.
  const view = healthScoreExplanation(projected.run);
  assert.equal(view.available, true);
  assert.equal(view.finalScore, 58);
});

test("without paid access no breakdown is projected", () => {
  const locked = buildCustomerProjection({
    run: { id: "s1", scan_id: "s1", status: "complete", health_score: 58, health_score_explanation: SEALED },
    fixList: { id: "fl1" },
    fixItems: [],
    fullAccess: false,
    authorityVerified: false,
  });
  assert.equal(locked.run.health_score_explanation, undefined);
});

test("all five copies of the seal normalizer are the same function", () => {
  // The seal is an HMAC over whatever scoreExplanation() returns, so every
  // writer and customer/Grok reader that handles v5 must produce byte-identical
  // output. They are separate Base44 packages with no shared module, so drift
  // in any one copy can make an intact result fail its authority seal.
  const copies = [
    "base44/functions/persistDurableScanAuthorityV2/authoritySnapshot.js",
    "base44/functions/getCustomerScanResultV2/projection.js",
    "base44/functions/grokChat/authoritySnapshot.js",
    "base44/functions/persistDurableScanAuthority/authoritySnapshot.js",
    "base44/functions/getCustomerScanResult/projection.js",
  ].map((file) => {
    const source = fs.readFileSync(new URL(`../../${file}`, import.meta.url), "utf8");
    const from = source.indexOf("function scoreExplanation(value) {");
    assert.ok(from > -1, `${file} has no scoreExplanation`);
    return { file, body: source.slice(from, source.indexOf("\n}", from)) };
  });

  for (const copy of copies.slice(1)) {
    assert.equal(copy.body, copies[0].body, `${copy.file} has drifted from the writer's copy`);
  }
  // And they agree on the version they normalize to.
  for (const { file, body } of copies) {
    assert.ok(body.includes("SCORE_EXPLANATION_VERSION"), file);
  }
});

// ------------------------------------------------------------- on the page --

test("the page renders the breakdown from the shared reader", () => {
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  assert.match(page, /from "@\/lib\/healthScoreExplanation"/);
  assert.match(page, /healthScoreExplanation\(scanRecord\)/);
  assert.match(page, /Why this score\?/);
  // And the older-record case, which is the one that renders nothing at all if
  // the branch is dropped -- silently, because nothing was there before either.
  assert.match(page, /explanation\?\.legacy \? \(/);
  assert.match(page, /\{explanation\.legacyNote\}/);
});
