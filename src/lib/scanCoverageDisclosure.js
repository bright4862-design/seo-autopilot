const COVERAGE_KEYS = Object.freeze([
  "urls_attempted",
  "usable_html_pages",
  "verified_http_failures",
  "access_unverified_pages",
  "non_html_resources",
  "unique_retained_destinations",
]);

/**
 * Return only scanner-owned observed integer counters.
 *
 * Legacy fields are intentionally ignored: a retained-page count is not a
 * request-attempt count, and converting strings or ratios here would create a
 * browser-derived coverage contract that the signed scan never supplied.
 */
export function scanCoverageDisclosure(scan = {}) {
  const source = scan?.scan_coverage && typeof scan.scan_coverage === "object" && !Array.isArray(scan.scan_coverage)
    ? scan.scan_coverage
    : {};
  const output = {};
  for (const key of COVERAGE_KEYS) {
    const value = source[key];
    if (Number.isInteger(value) && value >= 0) output[key] = value;
  }
  return output;
}

export const SCAN_COVERAGE_KEYS = COVERAGE_KEYS;
