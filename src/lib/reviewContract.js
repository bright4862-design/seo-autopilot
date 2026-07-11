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
