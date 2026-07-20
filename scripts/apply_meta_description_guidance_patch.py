from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one exact match in {path}, found {count}: {old[:120]!r}")
    file_path.write_text(source.replace(old, new, 1), encoding="utf-8")


def regex_replace_once(path: str, pattern: str, replacement: str) -> None:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected one regex match in {path}, found {count}: {pattern[:120]!r}")
    file_path.write_text(updated, encoding="utf-8")


SCAN_FORM = "src/components/scan/ScanWebsiteForm.jsx"
FIX_LIST = "src/pages/FixList.jsx"
RECOVERY = "src/lib/scanStorageRecovery.js"

replace_once(
    SCAN_FORM,
    'const TEMPLATE_RULES = new Set(["client_rendering", "js_rendering", "canonical_missing", "canonical_to_other_url", "schema", "missing_h1", "image_alt_text", "missing_meta_description", "route_boundary_candidate_indexable", "internal_route_indexable"]);',
    'const TEMPLATE_RULES = new Set(["client_rendering", "js_rendering", "canonical_missing", "canonical_to_other_url", "schema", "missing_h1", "image_alt_text", "missing_meta_description", "empty_meta_description", "malformed_meta_description", "meta_description_unusable", "route_boundary_candidate_indexable", "internal_route_indexable"]);',
)

replace_once(
    SCAN_FORM,
    'page_count: Number(fix.page_count || affectedPages.length || 1) };',
    'metadata_state_counts: normalizeMetadataStateCounts(fix.metadata_state_counts), combined_rules: firstArray([fix.combined_rules]).map(String).slice(0, 8), grouping_explanation: cleanString(fix.grouping_explanation), page_count: Number(fix.page_count || affectedPages.length || 1) };',
)

replace_once(
    SCAN_FORM,
    'meta_description: clampText(page.meta_description || "", 240), meta_description_state: page.meta_description_state || "", metadata_evidence_version: page.metadata_evidence_version || "", title_evidence_version:',
    'meta_description: clampText(page.meta_description || "", 240), meta_description_state: page.meta_description_state || "", meta_description_element_count: Number(page.meta_description_element_count || 0), meta_description_values: firstArray([page.meta_description_values]).map(String).slice(0, 8), meta_description_duplicate: Boolean(page.meta_description_duplicate), metadata_evidence_version: page.metadata_evidence_version || "", title_evidence_version:',
)

new_grouping = r'''const META_DESCRIPTION_GAP_RULES = new Set(["missing_meta_description", "empty_meta_description", "malformed_meta_description", "meta_description_unusable"]);
const META_DESCRIPTION_STATE_BY_RULE = {
  missing_meta_description: "missing",
  empty_meta_description: "empty",
  malformed_meta_description: "malformed",
};

function normalizeMetadataStateCounts(value = {}) {
  const input = value && typeof value === "object" ? value : {};
  return {
    missing: Math.max(0, Number(input.missing || 0)),
    empty: Math.max(0, Number(input.empty || input.present_empty || 0)),
    malformed: Math.max(0, Number(input.malformed || 0)),
  };
}

function metadataStateCountsForFix(fix = {}) {
  const existing = normalizeMetadataStateCounts(fix.metadata_state_counts);
  if (existing.missing + existing.empty + existing.malformed > 0) return existing;
  const state = META_DESCRIPTION_STATE_BY_RULE[String(fix.rule || "").toLowerCase()];
  if (!state) return existing;
  const affectedCount = firstArray([fix.affected_pages]).length;
  const reportedCount = Math.max(Number(fix.page_count || 0), affectedCount, fix.page_url ? 1 : 0);
  return { ...existing, [state]: reportedCount };
}

function addMetadataStateCounts(left = {}, right = {}) {
  const a = normalizeMetadataStateCounts(left);
  const b = normalizeMetadataStateCounts(right);
  return { missing: a.missing + b.missing, empty: a.empty + b.empty, malformed: a.malformed + b.malformed };
}

function metadataStateCountTotal(value = {}) {
  const counts = normalizeMetadataStateCounts(value);
  return counts.missing + counts.empty + counts.malformed;
}

function strongestPriority(left, right) {
  const rank = { critical: 4, high: 3, medium: 2, low: 1 };
  const a = normalizePriority(left);
  const b = normalizePriority(right);
  return (rank[b] || 0) > (rank[a] || 0) ? b : a;
}

function metaDescriptionFamilyLabel(family) {
  return String(family || "template").replace(/^activity_detail$/, "activity/detail").replace(/_/g, " ");
}

function metaDescriptionGroupCopy(family) {
  const label = metaDescriptionFamilyLabel(family);
  return {
    title: `Add usable meta descriptions to ${label} pages`,
    explanation: "Some pages are missing the meta-description tag, while others output a blank or invalid value. Because these pages use the same page pattern, fix the shared template rather than editing every URL one by one.",
    why: "Meta descriptions often appear beneath page titles in search results. When one is missing or blank, search engines must create their own snippet from page content. That snippet may be less specific or persuasive, giving the site less control over how each page is presented and potentially reducing qualified clicks. Fixing the shared template improves many pages at once.",
    recommendation: "Repair the shared metadata template so every affected page outputs exactly one non-empty, page-specific, plain-text meta description, with a reliable fallback when the dedicated SEO field is blank.",
    grouping: `All affected URLs use the ${label} page pattern. One template correction may resolve the problem across the entire group.`,
  };
}

function groupAndSortFixes(fixes, options = {}) {
  const normalized = Array.isArray(fixes) ? fixes.map((fix) => applyBusinessPriorityRules(fix, options)) : [];
  const groups = new Map();
  const keep = [];
  for (const fix of normalized) {
    const affectedCount = firstArray([fix.affected_pages]).length;
    const family = fix.page_template_family || classifyTemplateFamily(fix.page_url || fix.affected_pages?.[0] || "");
    const isMetaDescriptionGap = META_DESCRIPTION_GAP_RULES.has(String(fix.rule || "").toLowerCase());
    const shouldGroup = isMetaDescriptionGap || affectedCount >= 3 || TEMPLATE_RULES.has(fix.rule) || (fix.is_low_value_page && isCosmeticRule(fix));
    if (!shouldGroup) { keep.push(fix); continue; }
    const groupedRule = isMetaDescriptionGap ? "meta_description_unusable" : (fix.rule || fix.category);
    const key = isMetaDescriptionGap ? `${groupedRule}|${family}` : `${groupedRule}|${family}|${fix.priority}`;
    const copy = isMetaDescriptionGap ? metaDescriptionGroupCopy(family) : null;
    const title = copy?.title || getTemplateGroupTitle(fix, family);
    const existing = groups.get(key) || { ...fix, id: stableId(`group_${key}`), fix_id: stableId(`group_${key}`), rule: groupedRule, page_url: "", title, issue_title: title, plain_english_explanation: copy?.explanation || getTemplateGroupExplanation(fix), plain_english_summary: copy?.explanation || getTemplateGroupExplanation(fix), why_it_matters: copy?.why || getTemplateGroupWhy(fix), recommendation: copy?.recommendation || getTemplateGroupRecommendation(fix), recommended_value: copy?.recommendation || getTemplateGroupRecommendation(fix), simple_next_step: copy?.recommendation || getTemplateGroupRecommendation(fix), grouping_explanation: copy?.grouping || "", combined_rules: [], metadata_state_counts: { missing: 0, empty: 0, malformed: 0 }, affected_pages: [], source_pages: [], link_text_samples: [], page_count: 0, difficulty: needsDeveloperOwner(fix) ? "developer" : fix.difficulty, status: needsDeveloperOwner(fix) ? "needs_developer" : fix.status, requires_developer: needsDeveloperOwner(fix) || fix.requires_developer, requires_approval: needsDeveloperOwner(fix) ? false : fix.requires_approval, who_can_do_this: needsDeveloperOwner(fix) ? "your_web_person" : fix.who_can_do_this };
    existing.affected_pages = unique([...existing.affected_pages, ...firstArray([fix.affected_pages]), fix.page_url].filter(Boolean).map(String)).slice(0, 150);
    existing.source_pages = unique([...firstArray([existing.source_pages]), ...firstArray([fix.source_pages])]).slice(0, 30);
    existing.link_text_samples = unique([...firstArray([existing.link_text_samples]), ...firstArray([fix.link_text_samples])]).slice(0, 20);
    existing.requires_developer = existing.requires_developer || needsDeveloperOwner(fix) || fix.requires_developer;
    if (existing.requires_developer) {
      existing.requires_approval = false;
      existing.difficulty = "developer";
      existing.status = "needs_developer";
      existing.who_can_do_this = "your_web_person";
    }
    if (isMetaDescriptionGap) {
      existing.priority = strongestPriority(existing.priority, fix.priority);
      existing.metadata_state_counts = addMetadataStateCounts(existing.metadata_state_counts, metadataStateCountsForFix(fix));
      existing.combined_rules = unique([...firstArray([existing.combined_rules]), ...firstArray([fix.combined_rules]), fix.rule].filter(Boolean).map(String));
      existing.page_count = Math.max(existing.affected_pages.length, metadataStateCountTotal(existing.metadata_state_counts));
    } else {
      existing.page_count = existing.affected_pages.length;
    }
    groups.set(key, existing);
  }
  return dedupeFixes([...keep, ...Array.from(groups.values())]).sort((a, b) => businessSortScore(b, options) - businessSortScore(a, options));
}'''

regex_replace_once(
    SCAN_FORM,
    r'function groupAndSortFixes\(fixes, options = \{\}\) \{.*?\n\}\n\nfunction applyBusinessPriorityRules',
    new_grouping + '\n\nfunction applyBusinessPriorityRules',
)

replace_once(
    FIX_LIST,
    'const recommendations = useMemo(() => getRecommendations(scanRecord).map((item) => normalizeRecommendation(item, scanRecord)), [scanRecord]);',
    'const recommendations = useMemo(() => mergeMetaDescriptionRecommendations(getRecommendations(scanRecord).map((item) => normalizeRecommendation(item, scanRecord))), [scanRecord]);',
)

replace_once(
    FIX_LIST,
    '''          {evidenceItems.length > 0 ? (
            <>
              <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">What FixList confirmed</div>
              <p className="mt-1 max-w-[56ch] text-[13.5px]">
                {evidenceItems.map((entry) => `${entry.label}: ${entry.value}`).join(" · ")}
              </p>
            </>
          ) : null}

          <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">How to fix it</div>''',
    '''          {evidenceItems.length > 0 ? (
            <>
              <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">What FixList confirmed</div>
              <p className="mt-1 max-w-[56ch] text-[13.5px]">
                {evidenceItems.map((entry) => `${entry.label}: ${entry.value}`).join(" · ")}
              </p>
            </>
          ) : null}

          {item.groupingExplanation ? (
            <>
              <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Why these URLs are grouped</div>
              <p className="mt-1 max-w-[56ch] text-[13.5px]">{item.groupingExplanation}</p>
            </>
          ) : null}

          <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">How to fix it</div>''',
)

replace_once(
    FIX_LIST,
    '''    evidenceStatus: cleanString(item.evidence_status || item.verification_state),
    needsHelp,
    generalSteps: legacyBlocked429 ? build429Steps(evidence) : buildGeneralSteps(item, recommendation, needsHelp),''',
    '''    evidenceStatus: cleanString(item.evidence_status || item.verification_state),
    metadataStateCounts: normalizeMetadataStateCounts(item.metadata_state_counts),
    combinedRules: firstArray([item.combined_rules]).map(String),
    groupingExplanation: cleanString(item.grouping_explanation),
    needsHelp,
    generalSteps: legacyBlocked429 ? build429Steps(evidence) : buildGeneralSteps(item, recommendation, needsHelp),''',
)

meta_merge_helpers = r'''
const META_DESCRIPTION_GAP_RULES = new Set(["missing_meta_description", "empty_meta_description", "malformed_meta_description", "meta_description_unusable"]);
const META_DESCRIPTION_STATE_BY_RULE = {
  missing_meta_description: "missing",
  empty_meta_description: "empty",
  malformed_meta_description: "malformed",
};

function normalizeMetadataStateCounts(value = {}) {
  const input = value && typeof value === "object" ? value : {};
  return {
    missing: Math.max(0, Number(input.missing || 0)),
    empty: Math.max(0, Number(input.empty || input.present_empty || 0)),
    malformed: Math.max(0, Number(input.malformed || 0)),
  };
}

function metadataStateCountsForRecommendation(item = {}) {
  const existing = normalizeMetadataStateCounts(item.metadataStateCounts);
  if (existing.missing + existing.empty + existing.malformed > 0) return existing;
  const state = META_DESCRIPTION_STATE_BY_RULE[String(item.rule || "").toLowerCase()];
  if (!state) return existing;
  const count = Math.max(Number(item.pageCount || 0), item.affectedPages?.length || 0, 1);
  return { ...existing, [state]: count };
}

function addMetadataStateCounts(left = {}, right = {}) {
  const a = normalizeMetadataStateCounts(left);
  const b = normalizeMetadataStateCounts(right);
  return { missing: a.missing + b.missing, empty: a.empty + b.empty, malformed: a.malformed + b.malformed };
}

function metadataStateCountTotal(value = {}) {
  const counts = normalizeMetadataStateCounts(value);
  return counts.missing + counts.empty + counts.malformed;
}

function strongestPriority(left, right) {
  const rank = { critical: 4, high: 3, medium: 2, low: 1 };
  const a = normalizePriority(left);
  const b = normalizePriority(right);
  return (rank[b] || 0) > (rank[a] || 0) ? b : a;
}

function metaDescriptionFamilyLabel(family) {
  return String(family || "template").replace(/^activity_detail$/, "activity/detail").replace(/_/g, " ");
}

function metaDescriptionCopy(family) {
  const label = metaDescriptionFamilyLabel(family);
  return {
    title: `Add usable meta descriptions to ${label} pages`,
    explanation: "Some pages are missing the meta-description tag, while others output a blank or invalid value. Because these pages use the same page pattern, fix the shared template rather than editing every URL one by one.",
    why: "Meta descriptions often appear beneath page titles in search results. When one is missing or blank, search engines must create their own snippet from page content. That snippet may be less specific or persuasive, giving the site less control over how each page is presented and potentially reducing qualified clicks. Fixing the shared template improves many pages at once.",
    recommendation: "Repair the shared metadata template so every affected page outputs exactly one non-empty, page-specific, plain-text meta description, with a reliable fallback when the dedicated SEO field is blank.",
    grouping: `All affected URLs use the ${label} page pattern. One template correction may resolve the problem across the entire group.`,
  };
}

function mergeMetaDescriptionRecommendations(items = []) {
  const output = [];
  const groups = new Map();
  for (const item of items) {
    if (!META_DESCRIPTION_GAP_RULES.has(String(item.rule || "").toLowerCase())) {
      output.push(item);
      continue;
    }
    const family = item.templateFamily || "template";
    const key = `meta_description_unusable|${family}`;
    const copy = metaDescriptionCopy(family);
    const found = groups.get(key);
    if (!found) {
      const counts = metadataStateCountsForRecommendation(item);
      const merged = {
        ...item,
        id: stableId(key),
        rule: "meta_description_unusable",
        title: copy.title,
        explanation: copy.explanation,
        whyItMatters: copy.why,
        recommendation: copy.recommendation,
        groupingExplanation: copy.grouping,
        metadataStateCounts: counts,
        combinedRules: unique([...(item.combinedRules || []), item.rule].filter(Boolean)),
        pageCount: Math.max(item.affectedPages.length, metadataStateCountTotal(counts)),
      };
      groups.set(key, { index: output.length, item: merged });
      output.push(merged);
      continue;
    }
    const merged = found.item;
    merged.affectedPages = unique([...merged.affectedPages, ...item.affectedPages]);
    merged.sourcePages = unique([...merged.sourcePages, ...item.sourcePages]);
    merged.priority = strongestPriority(merged.priority, item.priority);
    merged.metadataStateCounts = addMetadataStateCounts(merged.metadataStateCounts, metadataStateCountsForRecommendation(item));
    merged.combinedRules = unique([...merged.combinedRules, ...(item.combinedRules || []), item.rule].filter(Boolean));
    merged.pageCount = Math.max(merged.affectedPages.length, metadataStateCountTotal(merged.metadataStateCounts));
    merged.needsHelp = merged.needsHelp || item.needsHelp;
    output[found.index] = merged;
  }
  return output;
}
'''

replace_once(
    FIX_LIST,
    '\nfunction extractRecommendationEvidence(item = {}, scanRecord = {}) {',
    meta_merge_helpers + '\nfunction extractRecommendationEvidence(item = {}, scanRecord = {}) {',
)

replace_once(
    FIX_LIST,
    '''  if (/missing_meta_description|empty_meta_description|malformed_meta_description/.test(rule) || category === "meta_description") return [
    "Export the affected URLs and group them by page template or CMS collection.",
    "Add a page-specific description field or repair the shared template so every affected page outputs one non-empty, plain-text meta description.",
    "Open representative page source from each group and confirm the description is present once and contains the expected text.",
    "Publish and run FixList again.",
  ];''',
    '''  if (/missing_meta_description|empty_meta_description|malformed_meta_description|meta_description_unusable/.test(rule) || category === "meta_description") return [
    "Use the status breakdown and URL export below to confirm which page groups are missing the tag, outputting an empty value, or using invalid markup.",
    "In the shared <head> metadata template, identify the source field used for each page's description, such as a dedicated SEO field, activity summary, category, or database value.",
    "Output exactly one non-empty, page-specific, plain-text meta description. When the dedicated SEO field is blank, build a reliable fallback from the page title or activity name, category, location, and main benefit.",
    "Strip HTML, placeholder text, line breaks, and repeated whitespace, and make sure the description appears in the initial server-rendered page source.",
    "Check a representative URL from each reported status, publish the change, and run FixList again.",
  ];''',
)

replace_once(
    FIX_LIST,
    '''function buildEvidenceItems(recommendation) {
  const items = [];
  if (recommendation.pageScope) items.push({ label: "Scope", value: humanize(recommendation.pageScope) });''',
    '''function buildEvidenceItems(recommendation) {
  const items = [];
  const metadataBreakdown = formatMetadataStateBreakdown(recommendation.metadataStateCounts);
  if (metadataBreakdown) items.push({ label: "Description status", value: metadataBreakdown });
  if (recommendation.pageScope) items.push({ label: "Scope", value: humanize(recommendation.pageScope) });''',
)

replace_once(
    FIX_LIST,
    '''  return items.slice(0, 6);
}

function readBestScanRecord''',
    '''  return items.slice(0, 6);
}

function formatMetadataStateBreakdown(value = {}) {
  const counts = normalizeMetadataStateCounts(value);
  return [
    counts.missing > 0 ? `${counts.missing} missing` : "",
    counts.empty > 0 ? `${counts.empty} empty` : "",
    counts.malformed > 0 ? `${counts.malformed} malformed` : "",
  ].filter(Boolean).join(" · ");
}

function readBestScanRecord''',
)

replace_once(
    RECOVERY,
    '''    page_template_family: fix.page_template_family || "",
    page_count: finiteNumber(fix.page_count, affectedPages.length),
  };''',
    '''    page_template_family: fix.page_template_family || "",
    metadata_state_counts: fix.metadata_state_counts && typeof fix.metadata_state_counts === "object"
      ? {
          missing: finiteNumber(fix.metadata_state_counts.missing),
          empty: finiteNumber(fix.metadata_state_counts.empty, fix.metadata_state_counts.present_empty),
          malformed: finiteNumber(fix.metadata_state_counts.malformed),
        }
      : {},
    combined_rules: firstArray(fix, ["combined_rules"]).map(String).slice(0, 8),
    grouping_explanation: String(fix.grouping_explanation || "").slice(0, 600),
    page_count: finiteNumber(fix.page_count, affectedPages.length),
  };''',
)

Path("tests/frontend/metaDescriptionGuidance.test.mjs").write_text(
    '''import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanFormSource = readFileSync(new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url), "utf8");
const fixListSource = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const recoverySource = readFileSync(new URL("../../src/lib/scanStorageRecovery.js", import.meta.url), "utf8");

test("missing, empty, and malformed descriptions become one customer task", () => {
  assert.match(scanFormSource, /META_DESCRIPTION_GAP_RULES/);
  assert.match(scanFormSource, /meta_description_unusable/);
  assert.match(scanFormSource, /Add usable meta descriptions to/);
  assert.match(fixListSource, /mergeMetaDescriptionRecommendations/);
  assert.match(fixListSource, /Why these URLs are grouped/);
});

test("the unified card explains search appearance without promising rankings", () => {
  assert.match(fixListSource, /search engines must create their own snippet/);
  assert.match(fixListSource, /potentially reducing qualified clicks/);
  assert.doesNotMatch(fixListSource, /meta descriptions improve rankings/i);
});

test("metadata state evidence survives browser and quota-safe persistence", () => {
  for (const field of ["meta_description_element_count", "meta_description_values", "meta_description_duplicate"]) {
    assert.match(scanFormSource, new RegExp(field));
  }
  for (const field of ["metadata_state_counts", "combined_rules", "grouping_explanation"]) {
    assert.match(scanFormSource, new RegExp(field));
    assert.match(recoverySource, new RegExp(field));
  }
});

test("fix instructions include template fallback and rendered-source verification", () => {
  assert.match(fixListSource, /build a reliable fallback/);
  assert.match(fixListSource, /initial server-rendered page source/);
  assert.match(fixListSource, /representative URL from each reported status/);
});
''',
    encoding="utf-8",
)

print("Applied unified meta-description guidance patch.")
