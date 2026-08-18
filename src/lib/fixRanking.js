const PRIORITY_RANK = Object.freeze({ critical: 4, high: 3, medium: 2, low: 1 });
const ACTION_RANK = Object.freeze({ fix_first: 4, important: 3, improve: 2, review: 1 });
const COVERING_SCOPES = new Set(["family", "cross_cutting", "sitewide"]);

function priorityOf(item = {}) {
  const value = String(item.baseSeverity || item.base_severity || item.priority || "").toLowerCase();
  return PRIORITY_RANK[value] ? value : "medium";
}

function actionPriorityOf(item = {}) {
  const value = String(
    item.actionPriority
      || item.action_priority
      || item.priorityContext?.action_priority
      || item.priority_context?.action_priority
      || item.original?.action_priority
      || "",
  ).toLowerCase();
  if (ACTION_RANK[value]) return value;
  const severity = priorityOf(item);
  if (severity === "critical" || severity === "high") return "fix_first";
  if (severity === "medium") return "important";
  return "improve";
}

function actionScoreOf(item = {}) {
  const raw = item.actionPriorityScore
    ?? item.action_priority_score
    ?? item.priorityContext?.action_priority_score
    ?? item.priority_context?.action_priority_score
    ?? item.original?.action_priority_score
    ?? 0;
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
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

/**
 * Stable customer presentation order.
 *
 * `priority` remains the technical/base severity. When the backend supplies the
 * contextual repair-priority contract, `action_priority` controls the customer
 * work queue and `action_priority_score` only orders work inside that band.
 * Legacy results fall back to the old severity-first behavior.
 */
export function rankFixesForCustomer(items = []) {
  return (Array.isArray(items) ? items : [])
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const actionDelta = ACTION_RANK[actionPriorityOf(right.item)] - ACTION_RANK[actionPriorityOf(left.item)];
      if (actionDelta !== 0) return actionDelta;
      const actionScoreDelta = actionScoreOf(right.item) - actionScoreOf(left.item);
      if (actionScoreDelta !== 0) return actionScoreDelta;
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
  const family = templateFamilyOf(item);
  const recommendation = recommendationOf(item);
  // Fail open for presentation: without an explicit page pattern AND an
  // explicit remediation, keep the evidence rows separate rather than risk
  // hiding genuinely different work behind one customer row.
  if (!rule || !family || !recommendation) return `ungrouped:${item.id || index}`;
  return `${rule}\u0000${family}\u0000${recommendation}`;
}

function strongerPriority(left, right) {
  return PRIORITY_RANK[priorityOf({ priority: right })] > PRIORITY_RANK[priorityOf({ priority: left })] ? right : left;
}

function sharedRepairConfirmed(item = {}) {
  if (item.sharedRepairConfirmed === true || item.shared_repair_confirmed === true || item.repair_leverage_confirmed === true) return true;
  const context = item.priorityContext || item.priority_context || item.original?.priority_context || {};
  return context?.shared_repair_confirmed === true;
}

/**
 * Merge separate evidence rows only when they resolve to the same customer action:
 * same rule, same page/template family, and same recommended remediation.
 * Scanner evidence remains untouched; this is presentation synthesis only.
 *
 * A shared page family is not proof that one CMS/template edit fixes everything.
 * The stronger "one shared change" language is reserved for explicit backend
 * repair-surface evidence.
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
      groups.set(key, {
        index: output.length,
        item: seeded,
        currentValues: new Set([String(item.currentValue || item.current_value || "").trim()].filter(Boolean)),
        sharedRepairConfirmed: sharedRepairConfirmed(item),
      });
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
    found.sharedRepairConfirmed = Boolean(found.sharedRepairConfirmed && sharedRepairConfirmed(item));

    const currentValue = String(item.currentValue || item.current_value || "").trim();
    if (currentValue) found.currentValues.add(currentValue);
    if (found.currentValues.size > 1) merged.currentValue = "";
    if (merged.groupedFindingCount > 1) {
      merged.groupingExplanation = found.sharedRepairConfirmed
        ? `FixList grouped ${merged.groupedFindingCount} related findings because they require the same confirmed shared repair. One shared change may improve ${merged.affectedPages.length} affected pages.`
        : `FixList grouped ${merged.groupedFindingCount} related findings because they share the same page pattern and recommended change. They remain traceable as separate findings; FixList has not assumed that one implementation change fixes every page.`;
      merged.sharedRepairConfirmed = found.sharedRepairConfirmed;
      merged.repairLeverageConfirmed = found.sharedRepairConfirmed;
    }
    output[found.index] = merged;
  });

  return output;
}

export function prepareCustomerFixes(items = []) {
  return rankFixesForCustomer(mergeSameActionFixes(suppressCoveredPageFixes(items)));
}

export function priorityBucket(value = "") {
  const actionValue = typeof value === "object" ? actionPriorityOf(value) : String(value || "").toLowerCase();
  if (ACTION_RANK[actionValue]) return actionValue;
  const severity = priorityOf({ priority: value });
  if (severity === "critical" || severity === "high") return "fix_first";
  if (severity === "medium") return "important";
  return "improve";
}

export function customerPriorityReason(item = {}) {
  return String(
    item.priorityReason
      || item.priority_reason
      || item.priorityContext?.priority_reason
      || item.priority_context?.priority_reason
      || item.original?.priority_reason
      || "",
  ).trim();
}
