export const ZERO_REPAIR_PRESENTATION_VERSION = "zero_repair_presentation_v1_explicit_evidence";

function clean(value = "") {
  return String(value || "").trim();
}

function explicitNoHighConfidenceFindingState(scan = {}) {
  return scan.no_high_confidence_findings === true
    || clean(scan.review_confidence_state).toLowerCase() === "no_high_confidence_findings"
    || clean(scan.scan_status).toLowerCase() === "complete_no_high_confidence_findings";
}

function authoritativeCompletedEvidence(scan = {}) {
  return clean(scan.status).toLowerCase() === "complete"
    && scan.release_gate_eligible === true
    && scan.is_authoritative === true
    && scan.score_is_provisional !== true
    && scan.evidence_quality_blocking !== true;
}

/**
 * Build an empty-repair customer state without treating an empty array as proof
 * that the website passed checks.
 *
 * A positive "no high-confidence issues" statement requires both an
 * authoritative completed scan and an explicit server-owned no-findings state.
 * Otherwise an empty repair array is merely an absence of customer repairs, not
 * evidence that rules ran, applied, and passed.
 */
export function zeroRepairPresentation(scan = {}, repairCount = 0) {
  const count = Math.max(0, Number(repairCount) || 0);
  if (count > 0) return null;

  const explicitNoFindings = authoritativeCompletedEvidence(scan)
    && explicitNoHighConfidenceFindingState(scan);

  if (explicitNoFindings) {
    return {
      version: ZERO_REPAIR_PRESENTATION_VERSION,
      state: "explicit_no_high_confidence_findings",
      positiveClaimAllowed: true,
      title: "No high-confidence issues found in the pages checked.",
      detail: clean(scan.next_best_step)
        || "FixList did not find a high-confidence repair in this checked sample. This does not mean every possible SEO check passed.",
    };
  }

  return {
    version: ZERO_REPAIR_PRESENTATION_VERSION,
    state: "empty_without_pass_evidence",
    positiveClaimAllowed: false,
    title: "No repairs to show from this saved result.",
    detail: "FixList does not treat an empty repair list as proof that every check passed.",
  };
}
