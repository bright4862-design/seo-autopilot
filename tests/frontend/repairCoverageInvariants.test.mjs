import assert from "node:assert/strict";
import test from "node:test";

import {
  REPAIR_INVARIANT_VERSION,
  firstFailedRepairInvariant,
  repairCoverageIsValid,
} from "../../base44/functions/persistDurableScanAuthority/repairInvariants.js";

/**
 * Patch D - Base44 rejects an impossible repair on its own arithmetic.
 *
 * Python computes the partitions; this side re-derives them and refuses a
 * payload whose numbers cannot be true. That independence is the point: a
 * forged or drifted payload must fail here even when the producer says it is
 * fine, so the tests below include cases Python would have accepted.
 *
 * Every displayed ratio is recomputed from integer cardinalities. A stored
 * rounded ratio is never trusted -- it is exactly the field an attacker or a
 * stale writer would set.
 */

function repair(overrides = {}) {
  return {
    rule: "missing_h1",
    page_scope: "family",
    page_template_family: "product_page",
    affected_pages: ["/p0", "/p1", "/p2"],
    page_count: 3,
    family_breakdown: { product_page: 3 },
    representative_pages_by_family: { product_page: "/p0" },
    affected_pages_complete: true,
    affected_reported: 3,
    affected_observed: 3,
    affected_eligible: 3,
    checked_eligible: 20,
    indexable_affected: 3,
    indexable_checked_eligible: 20,
    ...overrides,
  };
}

test("the invariant set is versioned", () => {
  assert.ok(REPAIR_INVARIANT_VERSION.startsWith("repair_invariant_"));
});

test("a well-formed repair passes", () => {
  assert.equal(firstFailedRepairInvariant(repair()), "");
  assert.equal(repairCoverageIsValid(repair()), true);
});

// ------------------------------------------------------ the cardinal order --

test("affected_eligible may not exceed affected_observed", () => {
  assert.equal(firstFailedRepairInvariant(repair({ affected_eligible: 4 })), "affected_eligible_exceeds_observed");
});

test("affected_observed may not exceed affected_reported", () => {
  assert.equal(
    firstFailedRepairInvariant(repair({ affected_observed: 5, affected_reported: 3 })),
    "affected_observed_exceeds_reported",
  );
});

test("affected_eligible may not exceed the denominator", () => {
  /** Wecandoo 126/1, Pretto 35/30, Meilleurtaux 47/6 all land here. */
  assert.equal(
    firstFailedRepairInvariant(repair({ affected_eligible: 126, affected_observed: 126, affected_reported: 126, checked_eligible: 1 })),
    "affected_eligible_exceeds_checked_eligible",
  );
});

test("indexable counts stay inside their own universe", () => {
  assert.equal(firstFailedRepairInvariant(repair({ indexable_affected: 4 })), "indexable_affected_exceeds_eligible");
  assert.equal(
    firstFailedRepairInvariant(repair({ indexable_checked_eligible: 21 })),
    "indexable_checked_eligible_exceeds_checked_eligible",
  );
});

test("a negative cardinality is refused", () => {
  assert.equal(firstFailedRepairInvariant(repair({ affected_eligible: -1 })), "negative_cardinality");
});

// -------------------------------------------------------- the partitions --

test("the breakdown must account for every affected page", () => {
  assert.equal(
    firstFailedRepairInvariant(repair({ family_breakdown: { product_page: 2 } })),
    "family_breakdown_does_not_sum_to_page_count",
  );
});

test("page_count must equal the unique affected pages", () => {
  assert.equal(
    firstFailedRepairInvariant(repair({ affected_pages: ["/p0", "/p0", "/p1"], page_count: 3 })),
    "page_count_disagrees_with_unique_affected_pages",
  );
});

test("URL identity is shared with Python, so ordering and tracking do not split a page", () => {
  const ok = repair({
    affected_pages: ["/p0?b=1&c=2", "/p1?utm_source=x", "/p2#top"],
    page_count: 3,
    // The representative is matched on the same identity, so it has to be
    // written as one of the affected pages actually is.
    representative_pages_by_family: { product_page: "/p0?c=2&b=1" },
  });
  assert.equal(firstFailedRepairInvariant(ok), "");

  const duplicated = repair({
    affected_pages: ["/p0?b=1&c=2", "/p0?c=2&b=1", "/p1"],
    page_count: 3,
    representative_pages_by_family: { product_page: "/p0?b=1&c=2" },
  });
  assert.equal(
    firstFailedRepairInvariant(duplicated),
    "page_count_disagrees_with_unique_affected_pages",
    "the same page written two ways is one page",
  );
});

// ------------------------------------------------------------- the scope --

test("family scope must name exactly one family", () => {
  assert.equal(
    firstFailedRepairInvariant(repair({ family_breakdown: { product_page: 2, guide_article: 1 } })),
    "family_scope_spans_multiple_families",
  );
});

test("page scope must have exactly one page", () => {
  assert.equal(
    firstFailedRepairInvariant(repair({ page_scope: "page" })),
    "page_scope_has_multiple_pages",
  );
});

test("mixed scope must actually carry partitions", () => {
  assert.equal(
    firstFailedRepairInvariant(repair({ page_scope: "mixed", page_template_family: "mixed" })),
    "mixed_scope_without_partitions",
  );
});

test("a representative must be one of the affected pages in its own family", () => {
  assert.equal(
    firstFailedRepairInvariant(repair({ representative_pages_by_family: { product_page: "/never-affected" } })),
    "representative_is_not_an_affected_page",
  );
});

// -------------------------------------------------------------- the ratio --

test("a truncated affected list suppresses its ratio rather than dividing a sample by a total", () => {
  const truncated = repair({ affected_pages: ["/p0", "/p1", "/p2"], page_count: 900, affected_pages_complete: false, family_breakdown: { product_page: 900 } });
  assert.equal(firstFailedRepairInvariant(truncated), "");
  assert.equal(repairCoverageIsValid(truncated), true);
});

test("a stored ratio is never trusted over the cardinalities", () => {
  /** The one field a forged payload would set. */
  const forged = repair({ checked_coverage: 0.01, affected_eligible: 126, affected_observed: 126, affected_reported: 126, checked_eligible: 1 });
  assert.equal(firstFailedRepairInvariant(forged), "affected_eligible_exceeds_checked_eligible");
});

test("a ratio above one is refused however it is expressed", () => {
  assert.equal(repairCoverageIsValid(repair({ affected_eligible: 30, affected_observed: 30, affected_reported: 35, checked_eligible: 6 })), false);
});

// ------------------------------------- Base44 rejects independently of Python --

import { firstFailedAuthorityPredicate } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

function authoritativeReview(recommendations) {
  return {
    archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
    review_version: "python_review_v2_structural_marketplace",
    review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
    ai_review_backend: "python_review_api",
    python_review_fallback_used: false,
    release_gate_eligible: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    metadata_evidence_version: "metadata_v1",
    title_evidence_version: "title_v1",
    site_fingerprint: {
      coverage_assessment: {
        state: "sufficient",
        coverage_authority_version: "coverage_authority_v1_shared_decision",
      },
    },
    recommendations,
  };
}

const AUTHORITATIVE_SCAN = {
  scanner_version: "python_scanner_v3_bounded_request",
  scanner_build_revision: "authenticated_health_probe_v1",
  advanced_scan_backend: "python_scanner_api",
  deno_fallback_used: false,
  beta_revision_fingerprint: RELEASE_FINGERPRINT,
  metadata_evidence_version: "metadata_v1",
  title_evidence_version: "title_v1",
};

test("a sound repair still seals", () => {
  assert.equal(firstFailedAuthorityPredicate(AUTHORITATIVE_SCAN, authoritativeReview([repair()])), "");
});

test("a forged 126-of-1 repair is refused even when everything else claims authority", () => {
  /**
   * The whole payload asserts it is release-authoritative. Base44 refuses it on
   * the repair's own arithmetic, which is the independence the blueprint asks
   * for: Python is not the only thing standing between a forged payload and a
   * seal.
   */
  const forged = repair({
    affected_reported: 126,
    affected_observed: 126,
    affected_eligible: 126,
    checked_eligible: 1,
    page_count: 126,
    family_breakdown: { homepage: 126 },
    affected_pages: Array.from({ length: 126 }, (unused, index) => `/w${index}`),
    representative_pages_by_family: { homepage: "/w0" },
    checked_coverage: 0.5,
  });

  assert.equal(firstFailedAuthorityPredicate(AUTHORITATIVE_SCAN, authoritativeReview([forged])), "repair_coverage_invariants");
});

test("one bad repair among many blocks the whole seal", () => {
  const review = authoritativeReview([repair(), repair({ affected_eligible: 99, checked_eligible: 1 }), repair()]);
  assert.equal(firstFailedAuthorityPredicate(AUTHORITATIVE_SCAN, review), "repair_coverage_invariants");
});
