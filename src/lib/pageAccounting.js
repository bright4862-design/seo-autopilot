const finiteCount = (value) => {
  const count = Number(value);
  return Number.isFinite(count) ? Math.max(0, Math.trunc(count)) : 0;
};

/**
 * Reconcile ranked section evidence to the authoritative discovery total.
 *
 * Focused-scan suggestions are intentionally filtered and bounded, so their
 * counts must never masquerade as a complete site inventory. Any pages those
 * suggestions do not name stay visible in one honest remainder row.
 */
export function buildPageAccounting(record = {}, sections = []) {
  const total = finiteCount(record?.pages_found);
  const seen = new Set();
  const namedRows = [];
  let remaining = total;
  let inconsistent = false;

  for (const section of Array.isArray(sections) ? sections : []) {
    const rawPrefix = String(section?.requested_path_prefix || "").trim();
    const key = rawPrefix.toLowerCase();
    if (!key || seen.has(key) || remaining <= 0) continue;
    seen.add(key);

    const reported = finiteCount(section?.discovered);
    if (reported <= 0) continue;
    if (reported > remaining) inconsistent = true;
    const count = Math.min(reported, remaining);
    namedRows.push({
      key,
      label: String(section?.label || "").trim() || rawPrefix,
      path: rawPrefix,
      count,
    });
    remaining -= count;
  }

  const remainder = remaining;
  const rows = remainder > 0
    ? [
        ...namedRows,
        { key: "other", label: "Homepage and other pages", path: "", count: remainder },
      ]
    : namedRows;

  return {
    total,
    namedTotal: total - remainder,
    remainder,
    rows,
    isPartial: remainder > 0 || inconsistent,
  };
}
