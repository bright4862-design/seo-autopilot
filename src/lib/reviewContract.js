export function hasAuthoritativePythonReview(aiData = {}) {
  return (
    aiData?.ai_review_backend === "python_review_api" &&
    aiData?.python_review_fallback_used !== true
  );
}

export function selectFinalReviewFixes({
  aiData = {},
  aiFixes = [],
  scannerFixes = [],
  slimFix = (fix) => fix,
  groupAndSortFixes,
  requestedPathPrefix = "",
} = {}) {
  const reviewed = Array.isArray(aiFixes) ? aiFixes : [];
  const scanner = Array.isArray(scannerFixes) ? scannerFixes : [];

  // Python Review already grouped, deduplicated, prioritized, titled, and assigned ownership.
  // Preserve that contract, including an authoritative empty result.
  if (hasAuthoritativePythonReview(aiData)) {
    return reviewed.map(slimFix).slice(0, 120);
  }

  // Legacy and fallback records still need the frontend compatibility layer.
  const source = reviewed.length > 0 ? reviewed : scanner;
  const normalized = source.map(slimFix);
  if (typeof groupAndSortFixes !== "function") return normalized.slice(0, 120);
  return groupAndSortFixes(normalized, { requestedPathPrefix }).slice(0, 120);
}


export function normalizeActionPriority(value) {
  const priority = String(value || "").toLowerCase();
  return ["critical", "high", "medium", "low"].includes(priority) ? priority : "medium";
}


export function normalizeReviewScope(fix = {}, fallbackFamily = "") {
  const explicitScope = String(fix?.page_scope || "").toLowerCase();
  const affected = Array.isArray(fix?.affected_pages) ? fix.affected_pages : [];
  const pageScope = ["sitewide", "cross_cutting", "family", "page"].includes(explicitScope)
    ? explicitScope
    : fix?.page_template_family === "mixed"
      ? "cross_cutting"
      : affected.length > 1
        ? "family"
        : "page";
  return {
    page_scope: pageScope,
    page_template_family: pageScope === "sitewide"
      ? ""
      : String(fix?.page_template_family || fallbackFamily || ""),
  };
}



export function isRateLimitFinding(fix = {}) {
  const rule = String(fix?.rule || fix?.issue_type || "").toLowerCase();
  const source = String(fix?.source || "").toLowerCase();
  const text = `${rule} ${fix?.category || ""} ${fix?.title || ""} ${fix?.issue_title || ""} ${fix?.current_value || ""} ${fix?.fetch_error || ""}`.toLowerCase();
  const status = Number(fix?.status_code || fix?.current_status_code || fix?.http_status || fix?.evidence?.status_code || 0);
  return (
    status === 429 ||
    ["rate_limited_page", "blocked_page", "blocked_page_429", "scanner_blocked"].includes(rule) ||
    source.startsWith("scanner_verified_failed_pages:429") ||
    text.includes("429") ||
    text.includes("rate limit") ||
    text.includes("rate-limit") ||
    text.includes("too many requests") ||
    text.includes("bot protection")
  );
}


export function shouldUseLegacyRateLimitPresentation(scanRecord = {}, fix = {}) {
  return isRateLimitFinding(fix) && !hasAuthoritativePythonReview(scanRecord);
}

export function normalizeFindingEvidence(fix = {}) {
  const rateLimited = isRateLimitFinding(fix);
  const explicitEvidence = String(fix?.evidence_status || "").toLowerCase();
  const evidenceStatus = explicitEvidence || (rateLimited ? "needs_verification" : "confirmed");
  return {
    evidence_status: evidenceStatus,
    verification_state: String(fix?.verification_state || "").toLowerCase() || evidenceStatus,
    limitation_code: String(fix?.limitation_code || "") || (rateLimited ? "rate_limit_requires_log_confirmation" : ""),
  };
}


export function normalizeReviewEvidenceState(source = {}) {
  const report = source?.website_health_report || {};
  const explicitStatus = String(source?.scan_status || report?.scan_status || "");
  const blocked = explicitStatus === "blocked_or_incomplete";
  const partial = explicitStatus === "complete_with_access_limitations";
  const incomplete = explicitStatus === "incomplete_evidence";
  const insufficient = explicitStatus === "inconclusive_insufficient_evidence";
  const noFindings = source?.no_high_confidence_findings === true || explicitStatus === "complete_no_high_confidence_findings";
  const scoreIsProvisional = Boolean(source?.score_is_provisional ?? report?.score_is_provisional) || blocked || partial || incomplete || insufficient;
  const accessEvidenceState = String(source?.access_evidence_state || report?.access_evidence_state || "") ||
    (blocked ? "blocked" : insufficient ? "insufficient_evidence" : partial ? "partial_access_limited" : "");
  const reviewConfidenceState = String(source?.review_confidence_state || report?.review_confidence_state || "") ||
    (blocked
      ? "blocked_access_needs_verification"
      : partial
        ? "partial_access_needs_verification"
        : incomplete
          ? "incomplete_evidence"
          : insufficient
            ? "insufficient_evidence"
          : noFindings
            ? "no_high_confidence_findings"
            : "");
  return {
    scan_status: explicitStatus,
    review_confidence_state: reviewConfidenceState,
    score_is_provisional: scoreIsProvisional,
    access_evidence_state: accessEvidenceState,
  };
}
