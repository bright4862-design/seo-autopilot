import { evidenceLink } from "./evidenceUrl.js";

/**
 * A compact, assistant-shaped export of one finished scan.
 *
 * The customer downloads this and uploads it to ChatGPT or Claude to be walked
 * through their fixes, so it carries the action and the reasoning rather than
 * the crawl. The stored scan record keeps up to 150 pages at roughly forty
 * fields each; shipping that would bury the handful of things the owner
 * actually has to do under several hundred kilobytes of telemetry, and a
 * pasted context window is exactly where that cost is felt.
 *
 * Everything here is already on the repair cards the page renders, so the
 * download can never describe a different scan than the one on screen.
 */

export const SCAN_HANDOFF_SCHEMA = "fixlist.scan_handoff.v1";

const MAX_FIXES = 50;
const MAX_EXAMPLE_PAGES = 10;
const MAX_LIMITATIONS = 5;

/**
 * Addressed to the assistant, not the customer. Without it a model tends to
 * summarize the file back; the owner wants to be taken through it.
 */
export const HANDOFF_INSTRUCTIONS = [
  "Each entry in \"fixes\" is one issue found by an automated SEO scan of the site named above, already ordered by priority.",
  "Walk the site owner through them one at a time, starting with the first. Explain what to change in plain language, then confirm they have done it before moving on.",
  "\"who_can_do_this\" says whether the owner can do it themselves or needs their web person. \"example_pages\" is a sample, not the complete list — \"pages_affected\" is the real count.",
  "Do not invent issues that are not in this file, and do not assume anything about pages that were not scanned.",
].join(" ");

function clean(value) {
  return String(value ?? "").trim();
}

function isoOrEmpty(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function positiveInt(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.trunc(number) : 0;
}

function textList(values, limit) {
  if (!Array.isArray(values)) return [];
  return values.map(clean).filter(Boolean).slice(0, limit);
}

/**
 * Reuses the same resolver the page and the PDF use, so an exported URL is the
 * one the customer can actually open. A page that is deliberately not
 * linkable falls back to its display label rather than being dropped, because
 * the count and the sample have to stay consistent with each other.
 */
function examplePages(pages, siteOrigin) {
  if (!Array.isArray(pages)) return [];
  const seen = new Set();
  const output = [];
  for (const page of pages) {
    if (output.length >= MAX_EXAMPLE_PAGES) break;
    const link = evidenceLink(page, siteOrigin);
    const value = link.href || link.label;
    if (!value || seen.has(value)) continue;
    seen.add(value);
    output.push(value);
  }
  return output;
}

function handoffFix(card = {}, index = 0, siteOrigin = "") {
  const evidence = card.evidence || {};
  const affected = Array.isArray(evidence.affectedPages) ? evidence.affectedPages : [];
  const samples = examplePages(affected, siteOrigin);
  // pageCount is the reported total, which can exceed the pages retained in a
  // saved result. Falling back to the retained length keeps the number honest
  // rather than reporting zero for a fix that clearly has evidence.
  const pagesAffected = positiveInt(evidence.pageCount) || affected.length;

  return {
    n: index + 1,
    title: clean(card.title) || "Review this recommendation",
    category: clean(card.customerCategory),
    priority: clean(card.priority) || "medium",
    who_can_do_this: clean(card.who) || "You",
    effort: clean(card.effort),
    why_it_matters: clean(card.whyItMatters),
    what_to_change: clean(card.whatToChange),
    where: clean(card.where),
    pages_affected: pagesAffected,
    example_pages: samples,
    example_pages_are_partial: pagesAffected > samples.length,
  };
}

/**
 * @returns a plain object safe to JSON.stringify. Callers pass the values the
 * page already computed so the export and the screen cannot disagree.
 */
export function buildScanHandoff({
  scanRecord = {},
  cards = [],
  healthScore = null,
  scoreUnavailable = false,
  pagesScanned = 0,
  pagesFound = 0,
  summary = "",
  nextBestStep = "",
  limitations = [],
  generatedAt = new Date(),
} = {}) {
  const siteOrigin = clean(scanRecord?.website_url);
  const list = Array.isArray(cards) ? cards.slice(0, MAX_FIXES) : [];

  return {
    schema: SCAN_HANDOFF_SCHEMA,
    how_to_use: HANDOFF_INSTRUCTIONS,
    generated_at: isoOrEmpty(generatedAt) || new Date().toISOString(),
    site: siteOrigin,
    scanned_at: isoOrEmpty(scanRecord?.created_at),
    pages_found: positiveInt(pagesFound),
    pages_checked: positiveInt(pagesScanned),
    // A provisional or unavailable score must not be exported as a number an
    // assistant would then reason about as if it were measured.
    health_score: scoreUnavailable ? null : (Number.isFinite(Number(healthScore)) ? Number(healthScore) : null),
    health_score_available: !scoreUnavailable,
    summary: clean(summary),
    next_best_step: clean(nextBestStep),
    limitations: textList(limitations, MAX_LIMITATIONS),
    fix_count: list.length,
    fix_count_is_partial: Array.isArray(cards) && cards.length > list.length,
    fixes: list.map((card, index) => handoffFix(card, index, siteOrigin)),
  };
}

export function scanHandoffFilename(scanRecord = {}) {
  const site = clean(scanRecord?.website_url)
    .replace(/^https?:\/\//i, "")
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  const day = (isoOrEmpty(scanRecord?.created_at) || new Date().toISOString()).slice(0, 10);
  return `fixlist-${site || "scan"}-${day}.json`;
}

export function serializeScanHandoff(handoff) {
  return `${JSON.stringify(handoff, null, 2)}\n`;
}
