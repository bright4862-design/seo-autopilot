/**
 * Deterministic Grok hand-off for one repair.
 *
 * Grok is an optional implementation assistant, never the diagnosis. FixList
 * has already decided what is wrong, how badly it matters, how the repairs are
 * grouped, and what the suggested fix is. This module packages that finished
 * decision as context and asks Grok for implementation help only.
 *
 * Nothing here calls a model, and nothing here can change a repair: the brief
 * is plain text built from the repair the customer is already looking at.
 */

import { GROK_MAX_MESSAGE_LENGTH } from "./grokChat.js";

export const GROK_REPAIR_BRIEF_VERSION = "grok_repair_brief_v1";
export const GROK_REPAIR_BRIEF_STORAGE_KEY = "seo_autopilot:grok_repair_brief";
export const GROK_REPAIR_BRIEF_MAX_URLS = 10;

const DIAGNOSIS_BOUNDARY = "FixList has already diagnosed and prioritized this repair. Do not re-diagnose it, re-rank it, or replace the suggested fix — give implementation steps for the platform above.";

function clean(value = "") {
  return String(value || "").trim();
}

function absoluteUrl(page = "", websiteUrl = "") {
  const path = clean(page);
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const base = clean(websiteUrl);
  if (!base) return path;
  try {
    return new URL(path, base.startsWith("http") ? base : `https://${base}`).toString();
  } catch {
    return path;
  }
}

function affectedPagesOf(item = {}) {
  const values = item.affectedPages || item.affected_pages || item.original?.affected_pages || [];
  return Array.isArray(values) ? values.filter(Boolean).map(String) : [];
}

function pageCountOf(item = {}) {
  const reported = Number(item.pageCount ?? item.page_count ?? item.original?.page_count ?? 0);
  return Math.max(Number.isFinite(reported) ? reported : 0, affectedPagesOf(item).length);
}

/**
 * The structured context handed to Grok.
 *
 * Every field is copied from the repair FixList already computed. Grok receives
 * the diagnosis; it does not produce one.
 */
export function grokRepairBriefContext({
  item = {},
  model = {},
  suggestion = {},
  scan = {},
  platform = "",
  maxUrls = GROK_REPAIR_BRIEF_MAX_URLS,
} = {}) {
  const websiteUrl = clean(scan?.website_url || item.websiteUrl || item.website_url);
  const pages = affectedPagesOf(item);
  const limit = Math.max(1, Number(maxUrls) || GROK_REPAIR_BRIEF_MAX_URLS);

  return {
    version: GROK_REPAIR_BRIEF_VERSION,
    diagnosisOwner: "fixlist",
    grokRole: "implementation_help",
    repairTitle: clean(model.title || item.title || item.issue_title) || "FixList repair",
    priority: clean(model.sectionLabel),
    impact: clean(model.reason || item.whyItMatters || item.why_it_matters),
    whyItMatters: clean(item.whyItMatters || item.why_it_matters),
    suggestedFix: clean(suggestion.suggestedFix),
    bestApproach: clean(suggestion.bestApproach),
    fixStrategy: clean(suggestion.fixStrategy),
    effort: clean(suggestion.effortLabel),
    recommendedRole: clean(suggestion.recommendedRole),
    suggestionAvailable: suggestion.suggestionAvailable === true,
    suggestionLibraryVersion: clean(suggestion.libraryVersion),
    repairType: clean(suggestion.repairType),
    rule: clean(item.rule || item.original?.rule),
    surface: clean(model.surface),
    scope: clean(model.scope),
    evidence: clean(item.explanation || item.plain_english_explanation),
    platform: clean(platform),
    websiteUrl,
    affectedPageCount: pageCountOf(item),
    affectedUrls: pages.slice(0, limit).map((page) => absoluteUrl(page, websiteUrl)).filter(Boolean),
  };
}

/**
 * Optional context, in the order it is given up when the brief is too long.
 *
 * The repair title, priority, platform, suggested fix, and the diagnosis
 * boundary are never in this list: those are what make the message a FixList
 * hand-off rather than an open-ended question, so they always survive.
 */
const OPTIONAL_SECTIONS = Object.freeze(["urls", "rule", "evidence", "impact", "role", "effort", "approach"]);

function briefBody(context, omitted = new Set()) {
  const lines = [
    "I need help implementing a repair from my FixList.",
    "",
    `Repair: ${context.repairTitle}`,
  ];

  if (context.priority) lines.push(`Priority: ${context.priority}`);
  if (context.surface || context.scope) {
    lines.push(`Affected: ${[context.surface, context.scope].filter(Boolean).join(" · ")}`);
  }
  if (context.platform) lines.push(`Platform: ${context.platform}`);
  if (context.rule && !omitted.has("rule")) lines.push(`FixList rule: ${context.rule}`);
  if (context.impact && !omitted.has("impact")) lines.push(`Why this matters: ${context.impact}`);
  if (context.evidence && context.evidence !== context.impact && !omitted.has("evidence")) {
    lines.push(`Evidence: ${context.evidence}`);
  }
  lines.push(`FixList suggested fix: ${context.suggestedFix}`);
  if (context.bestApproach && !omitted.has("approach")) lines.push(`Best approach: ${context.bestApproach}`);
  if (context.effort && !omitted.has("effort")) lines.push(`Expected effort: ${context.effort}`);
  if (context.recommendedRole && !omitted.has("role")) lines.push(`Usually done by: ${context.recommendedRole}`);
  if (!context.suggestionAvailable) {
    lines.push("Note: FixList has no stored suggested fix for this rule yet, so treat the evidence above as the source of truth.");
  }

  if (context.affectedUrls.length > 0 && !omitted.has("urls")) {
    const shown = context.affectedUrls.length;
    const total = Math.max(context.affectedPageCount, shown);
    lines.push("");
    lines.push(shown < total ? `Affected pages (${shown} of ${total}):` : `Affected pages (${shown}):`);
    for (const url of context.affectedUrls) lines.push(`- ${url}`);
  }

  return lines.join("\n");
}

/**
 * Render the brief as a single message that fits Grok's limit.
 *
 * Affected URLs are thinned first, then optional context is dropped in a fixed
 * order. The suggested fix and the "FixList already diagnosed this" boundary
 * are reserved, so a long repair can never turn the hand-off into an
 * open-ended request for a diagnosis.
 */
export function buildGrokRepairBrief(input = {}) {
  const maxLength = Math.max(200, Number(input.maxLength) || GROK_MAX_MESSAGE_LENGTH);
  const boundaryBlock = `\n\n${DIAGNOSIS_BOUNDARY}`;
  const bodyBudget = Math.max(1, maxLength - boundaryBlock.length);
  const requestedUrls = Math.max(1, Number(input.maxUrls) || GROK_REPAIR_BRIEF_MAX_URLS);

  const omitted = new Set();
  let urlLimit = requestedUrls;
  let body = briefBody(grokRepairBriefContext({ ...input, maxUrls: urlLimit }), omitted);

  while (body.length > bodyBudget && urlLimit > 1) {
    urlLimit = Math.floor(urlLimit / 2);
    body = briefBody(grokRepairBriefContext({ ...input, maxUrls: urlLimit }), omitted);
  }

  for (const section of OPTIONAL_SECTIONS) {
    if (body.length <= bodyBudget) break;
    omitted.add(section);
    body = briefBody(grokRepairBriefContext({ ...input, maxUrls: urlLimit }), omitted);
  }

  return `${body.slice(0, bodyBudget)}${boundaryBlock}`;
}

/**
 * Hand the brief to the assistant page without sending it.
 *
 * The customer still presses send, so Grok stays optional and never runs on its
 * own. The brief lives in sessionStorage only, and is listed in the customer
 * cache keys so signing out clears it.
 */
export function stashGrokRepairBrief(brief, browserWindow = globalThis.window) {
  const text = clean(brief);
  if (!text || !browserWindow?.sessionStorage) return false;
  try {
    browserWindow.sessionStorage.setItem(GROK_REPAIR_BRIEF_STORAGE_KEY, text);
    return true;
  } catch {
    return false;
  }
}

export function takeGrokRepairBrief(browserWindow = globalThis.window) {
  if (!browserWindow?.sessionStorage) return "";
  try {
    const value = clean(browserWindow.sessionStorage.getItem(GROK_REPAIR_BRIEF_STORAGE_KEY));
    browserWindow.sessionStorage.removeItem(GROK_REPAIR_BRIEF_STORAGE_KEY);
    return value.slice(0, GROK_MAX_MESSAGE_LENGTH);
  } catch {
    return "";
  }
}
