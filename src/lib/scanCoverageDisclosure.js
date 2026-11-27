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

export function recordedPageCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function checkedFolderRows(scan = {}) {
  const evidence = scan?.sampling_evidence;
  const checked = evidence?.path_prefixes_checked;
  if (!checked || typeof checked !== "object" || Array.isArray(checked)) return [];
  const selected = evidence.path_prefixes_selected ?? evidence.path_prefixes_sampled;

  return Object.entries(checked)
    .filter(([path, value]) => /^\/[^/?#]+$/.test(path) && recordedPageCount(value) !== null)
    .map(([path, value]) => ({
      path,
      found: recordedPageCount(evidence.path_prefixes_discovered?.[path]),
      selected: recordedPageCount(selected?.[path]),
      checked: value,
    }))
    .sort((a, b) => b.checked - a.checked || a.path.localeCompare(b.path));
}

export const SCAN_COVERAGE_KEYS = COVERAGE_KEYS;
