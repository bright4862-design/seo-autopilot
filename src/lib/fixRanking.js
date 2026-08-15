const PRIORITY_RANK = Object.freeze({ critical: 4, high: 3, medium: 2, low: 1 });
const COVERING_SCOPES = new Set(["family", "cross_cutting", "sitewide"]);

function priorityOf(item = {}) {
  const value = String(item.priority || "").toLowerCase();
  return PRIORITY_RANK[value] ? value : "medium";
}

function affectedPagesOf(item = {}) {
  if (Array.isArray(item.affectedPages)) return item.affectedPages.filter(Boolean).map(String);
  if (Array.isArray(item.affected_pages)) return item.affected_pages.filter(Boolean).map(String);
  return [];
}

function pageCountOf(item = {}) {
  const available = affectedPagesOf(item).length;
  const reported = Number(item.pageCount ?? item.page_count ?? 0);
  return Math.max(Number.isFinite(reported) ? reported : 0, available);
}

function confidenceOf(item = {}) {
  const raw = item.confidenceScore ?? item.confidence_score ?? item.original?.confidence_score ?? 0;
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}

function ruleOf(item = {}) {
  return String(item.rule || item.original?.rule || "").trim().toLowerCase();
}

function scopeOf(item = {}) {
  return String(item.pageScope || item.page_scope || item.original?.page_scope || "page").trim().toLowerCase() || "page";
}

function normalizePageKey(value = "") {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw, "https://fixlist.invalid");
    return `${url.pathname || "/"}${url.search || ""}`.replace(/\/$/, "") || "/";
  } catch {
    return raw.replace(/^https?:\/\/[^/]+/i, "").replace(/\/$/, "") || "/";
  }
}

/**
 * Hide a page-level card only when a broader card for the SAME RULE explicitly
 * includes that page. Never dedupe across rules: page overlap alone does not
 * make two findings equivalent.
 */
export function suppressCoveredPageFixes(items = []) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  const coverageByRule = new Map();

  for (const item of list) {
    const scope = scopeOf(item);
    const rule = ruleOf(item);
    if (!rule || !COVERING_SCOPES.has(scope)) continue;
    const pages = affectedPagesOf(item).map(normalizePageKey).filter(Boolean);
    if (pages.length === 0) continue;
    const covered = coverageByRule.get(rule) || new Set();
    for (const page of pages) covered.add(page);
    coverageByRule.set(rule, covered);
  }

  return list.filter((item) => {
    if (scopeOf(item) !== "page") return true;
    const rule = ruleOf(item);
    const covered = coverageByRule.get(rule);
    if (!covered || covered.size === 0) return true;
    const pages = affectedPagesOf(item);
    const representative = pages[0] || item.pageUrl || item.page_url || item.original?.page_url || "";
    const key = normalizePageKey(representative);
    return !key || !covered.has(key);
  });
}

/** Stable customer presentation order. Scanner/review priority is never changed. */
export function rankFixesForCustomer(items = []) {
  return (Array.isArray(items) ? items : [])
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const priorityDelta = PRIORITY_RANK[priorityOf(right.item)] - PRIORITY_RANK[priorityOf(left.item)];
      if (priorityDelta !== 0) return priorityDelta;
      const scopeDelta = pageCountOf(right.item) - pageCountOf(left.item);
      if (scopeDelta !== 0) return scopeDelta;
      const confidenceDelta = confidenceOf(right.item) - confidenceOf(left.item);
      if (confidenceDelta !== 0) return confidenceDelta;
      return left.index - right.index;
    })
    .map(({ item }) => item);
}

function templateFamilyOf(item = {}) {
  return String(item.templateFamily || item.page_template_family || item.original?.page_template_family || "").trim().toLowerCase();
}

function recommendationOf(item = {}) {
  return String(item.recommendation || item.recommended_value || item.original?.recommended_value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function uniqueStrings(values = []) {
  return Array.from(new Set(values.filter(Boolean).map(String)));
}

function actionKeyOf(item = {}, index = 0) {
  const rule = ruleOf(item);
  if (!rule) return `ungrouped:${item.id || index}`;
  const family = templateFamilyOf(item) || "unclassified";
  const recommendation = recommendationOf(item) || String(item.title || item.issue_title || "").trim().toLowerCase();
  return `${rule}\u0000${family}\u0000${recommendation}`;
}

function strongerPriority(left, right) {
  return PRIORITY_RANK[priorityOf({ priority: right })] > PRIORITY_RANK[priorityOf({ priority: left })] ? right : left;
}

/**
 * Merge separate evidence rows only when they resolve to the same customer action:
 * same rule, same page/template family, and same recommended remediation.
 * Scanner evidence remains untouched; this is presentation synthesis only.
 */
export function mergeSameActionFixes(items = []) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  const groups = new Map();
  const output = [];

  list.forEach((item, index) => {
    const key = actionKeyOf(item, index);
    const found = groups.get(key);
    if (!found) {
      const seeded = {
        ...item,
        affectedPages: uniqueStrings(affectedPagesOf(item)),
        sourcePages: uniqueStrings(item.sourcePages || item.source_pages || []),
        memberIds: uniqueStrings([item.id]),
        groupedFindingCount: 1,
      };
      seeded.pageCount = Math.max(pageCountOf(item), seeded.affectedPages.length);
      groups.set(key, { index: output.length, item: seeded, currentValues: new Set([String(item.currentValue || item.current_value || "").trim()].filter(Boolean)) });
      output.push(seeded);
      return;
    }

    const merged = found.item;
    merged.affectedPages = uniqueStrings([...merged.affectedPages, ...affectedPagesOf(item)]);
    merged.sourcePages = uniqueStrings([...merged.sourcePages, ...(item.sourcePages || item.source_pages || [])]);
    merged.memberIds = uniqueStrings([...merged.memberIds, item.id]);
    merged.groupedFindingCount += 1;
    merged.pageCount = Math.max(merged.affectedPages.length, pageCountOf(merged), pageCountOf(item));
    merged.priority = strongerPriority(merged.priority, item.priority);
    merged.confidenceScore = Math.max(confidenceOf(merged), confidenceOf(item));
    merged.needsHelp = Boolean(merged.needsHelp || item.needsHelp);
    merged.combinedRules = uniqueStrings([...(merged.combinedRules || []), ...(item.combinedRules || []), ruleOf(item)]);

    const currentValue = String(item.currentValue || item.current_value || "").trim();
    if (currentValue) found.currentValues.add(currentValue);
    if (found.currentValues.size > 1) merged.currentValue = "";
    if (merged.groupedFindingCount > 1) {
      merged.groupingExplanation = `FixList grouped ${merged.groupedFindingCount} related findings because they use the same page pattern and require the same change. One fix can address all ${merged.affectedPages.length} affected pages.`;
    }
    output[found.index] = merged;
  });

  return output;
}

export function prepareCustomerFixes(items = []) {
  return rankFixesForCustomer(mergeSameActionFixes(suppressCoveredPageFixes(items)));
}

export function priorityBucket(priority = "") {
  const value = priorityOf({ priority });
  if (value === "critical" || value === "high") return "fix_first";
  if (value === "medium") return "improve_next";
  return "worth_checking";
}
