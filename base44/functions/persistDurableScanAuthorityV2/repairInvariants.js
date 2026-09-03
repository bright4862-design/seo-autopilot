import { evidenceUrlKey } from "./evidenceUrlIdentity.js";

/**
 * Base44 refuses an impossible repair on its own arithmetic.
 *
 * Python computes a repair's partitions; this side re-derives them and rejects a
 * payload whose numbers cannot be true. The independence is the point: a forged
 * or drifted payload has to fail here even when the producer says it is fine.
 *
 * Every ratio is recomputed from integer cardinalities. A stored rounded ratio
 * is never read -- it is precisely the field a forged payload would set, and it
 * carries no evidence of its own.
 */

export const REPAIR_INVARIANT_VERSION = "repair_invariant_v1_family_consistent_coverage";

const NON_SPECIFIC_FAMILIES = new Set(["", "mixed", "sitewide", "cross_cutting", "unknown"]);

function count(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : 0;
}

function optionalCount(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}

function uniqueAffectedKeys(repair) {
  const keys = new Set();
  for (const url of repair?.affected_pages || []) {
    const key = evidenceUrlKey(url);
    if (key) keys.add(key);
  }
  return keys;
}

function breakdown(repair) {
  const raw = repair?.family_breakdown;
  return raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
}

/**
 * The first invariant this repair violates, or "" when it is sound.
 *
 * Returns a name rather than a boolean so a rejection can say what was wrong
 * without the caller re-deriving it, and so a new invariant cannot be added
 * without a name that appears in the logs.
 */
export function firstFailedRepairInvariant(repair) {
  if (!repair || typeof repair !== "object") return "repair_missing";

  const reported = count(repair.affected_reported ?? repair.page_count);
  const observed = count(repair.affected_observed ?? reported);
  const eligible = count(repair.affected_eligible ?? observed);
  const checkedEligible = optionalCount(repair.checked_eligible);
  const indexableAffected = count(repair.indexable_affected);
  const indexableEligible = optionalCount(repair.indexable_checked_eligible);
  const pageCount = count(repair.page_count);
  const scope = String(repair.page_scope || "").toLowerCase();
  const partitions = breakdown(repair);
  const complete = repair.affected_pages_complete !== false;

  const cardinalities = [reported, observed, eligible, indexableAffected, pageCount];
  if (cardinalities.some((value) => value < 0)) return "negative_cardinality";
  if (checkedEligible !== null && checkedEligible < 0) return "negative_cardinality";
  if (indexableEligible !== null && indexableEligible < 0) return "negative_cardinality";

  // 0 <= affected_eligible <= affected_observed <= affected_reported
  if (observed > reported) return "affected_observed_exceeds_reported";
  if (eligible > observed) return "affected_eligible_exceeds_observed";
  if (checkedEligible !== null && eligible > checkedEligible) return "affected_eligible_exceeds_checked_eligible";
  if (indexableAffected > eligible) return "indexable_affected_exceeds_eligible";
  if (indexableEligible !== null && checkedEligible !== null && indexableEligible > checkedEligible) {
    return "indexable_checked_eligible_exceeds_checked_eligible";
  }
  if (indexableEligible !== null && indexableAffected > indexableEligible) {
    return "indexable_affected_exceeds_indexable_checked_eligible";
  }

  const partitionTotal = Object.values(partitions).reduce((total, value) => total + count(value), 0);
  if (Object.keys(partitions).length > 0 && partitionTotal !== pageCount) {
    return "family_breakdown_does_not_sum_to_page_count";
  }

  // A truncated list is a sample; only a complete one can be counted against
  // page_count, and its ratio is suppressed rather than compared with a total.
  if (complete && uniqueAffectedKeys(repair).size !== pageCount) {
    return "page_count_disagrees_with_unique_affected_pages";
  }

  const namedFamilies = Object.keys(partitions).filter((family) => !NON_SPECIFIC_FAMILIES.has(family));
  if (scope === "page" && pageCount > 1) return "page_scope_has_multiple_pages";
  if (scope === "family" && Object.keys(partitions).length > 1) return "family_scope_spans_multiple_families";
  if (scope === "mixed") {
    const partitionNames = new Set(Object.keys(partitions).map((family) => String(family || "").trim().toLowerCase()));
    const unknownOnlyMultiPage = pageCount > 1 && partitionNames.size === 1 && partitionNames.has("unknown");
    if (Object.keys(partitions).length < 2 && !unknownOnlyMultiPage) return "mixed_scope_without_partitions";
  }

  const representatives = repair.representative_pages_by_family;
  if (representatives && typeof representatives === "object" && complete) {
    const affected = uniqueAffectedKeys(repair);
    for (const [family, value] of Object.entries(representatives)) {
      const urls = Array.isArray(value) ? value : [value];
      if (urls.length === 0) return "representative_is_not_an_affected_page";
      for (const url of urls) {
        if (!affected.has(evidenceUrlKey(url))) return "representative_is_not_an_affected_page";
      }
      if (namedFamilies.length && !(family in partitions)) return "representative_family_not_in_breakdown";
    }
  }

  return "";
}

export function repairCoverageIsValid(repair) {
  return firstFailedRepairInvariant(repair) === "";
}

/**
 * The coverage ratio, recomputed. Null whenever it cannot be stated honestly:
 * no denominator, an incomplete affected list, or a repair that fails its own
 * invariants. The caller renders an absolute count instead.
 */
export function recomputedCoverageRatio(repair) {
  if (!repairCoverageIsValid(repair)) return null;
  if (repair?.affected_pages_complete === false) return null;
  const checkedEligible = optionalCount(repair?.checked_eligible);
  if (checkedEligible === null || checkedEligible <= 0) return null;
  const eligible = count(repair?.affected_eligible ?? repair?.affected_observed ?? repair?.page_count);
  const ratio = eligible / checkedEligible;
  return ratio >= 0 && ratio <= 1 ? ratio : null;
}
