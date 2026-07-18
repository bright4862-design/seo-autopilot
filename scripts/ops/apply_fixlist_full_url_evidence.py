from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise SystemExit(f"{path}: replacement markers drifted: {start!r} / {end!r}")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    updated = text[:start_index] + replacement.rstrip() + "\n\n" + text[end_index:]
    target.write_text(updated, encoding="utf-8")


fixlist_path = "src/pages/FixList.jsx"
replace_once(
    fixlist_path,
    'import { Bug, Copy, ExternalLink, RefreshCw, Trash2 } from "lucide-react";',
    'import { Bug, Copy, Download, ExternalLink, RefreshCw, Trash2 } from "lucide-react";',
)

replace_between(
    fixlist_path,
    "function FixRow({ item, cms, onDone }) {\n",
    "function PassedChecks({ checks }) {\n",
    r'''function FixRow({ item, cms, onDone }) {
  const [open, setOpen] = useState(false);
  const [showAllPages, setShowAllPages] = useState(false);
  const [copied, setCopied] = useState(false);
  const severe = item.priority === "critical" || item.priority === "high";
  const cmsSteps = getCmsSteps(cms, item);
  const evidenceItems = buildEvidenceItems(item).slice(0, 4);
  const availableCount = item.affectedPages.length;
  const reportedCount = Math.max(Number(item.pageCount || 0), availableCount);
  const shownPages = showAllPages ? item.affectedPages : item.affectedPages.slice(0, 8);
  const extraCount = Math.max(0, availableCount - shownPages.length);

  async function copyAffectedUrls() {
    try {
      const text = item.affectedPages.map((page) => toAbsolutePageUrl(page, item.websiteUrl)).join("\n");
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.warn("Could not copy affected URLs.", error);
    }
  }

  function downloadAffectedUrls() {
    const rows = item.affectedPages.map((page) => [
      toAbsolutePageUrl(page, item.websiteUrl),
      item.title,
      item.rule,
      item.priority,
      item.templateFamily,
    ]);
    const csv = [
      ["affected_url", "finding", "rule", "priority", "template_family"],
      ...rows,
    ].map((row) => row.map(csvCell).join(",")).join("\n");
    const host = safeHostname(item.websiteUrl) || "website";
    const rule = String(item.rule || "finding").replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
    downloadTextFile(csv, `fixlist-${host}-${rule || "finding"}-urls.csv`, "text/csv;charset=utf-8");
  }

  return (
    <div className="border-b border-hairline-soft">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start gap-3.5 py-5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        <span className={`mt-[7px] h-[7px] w-[7px] shrink-0 rounded-full ${severe ? "bg-crit" : "bg-warnink"}`} />
        <span className="min-w-0 flex-1">
          <span className="block text-[16px] font-medium tracking-tight">{item.title}</span>
          <span className="mt-0.5 block text-[13.5px] text-ink-muted">{clampText(item.explanation, 110)}</span>
        </span>
        <span className="mt-0.5 flex shrink-0 items-center gap-3">
          <span className="hidden text-[12px] text-ink-faint sm:block">{item.needsHelp ? "Developer" : "You"}</span>
          <span className={`text-[12px] leading-none text-ink-faint transition-transform ${open ? "rotate-90" : ""}`}>›</span>
        </span>
      </button>

      {open ? (
        <div className="pb-6 pl-[21px] text-[14px] text-ink-muted">
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">Why this matters</div>
          <p className="mt-1 max-w-[56ch]">{item.whyItMatters}</p>

          {evidenceItems.length > 0 ? (
            <>
              <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">What FixList confirmed</div>
              <p className="mt-1 max-w-[56ch] text-[13.5px]">
                {evidenceItems.map((entry) => `${entry.label}: ${entry.value}`).join(" · ")}
              </p>
            </>
          ) : null}

          <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">How to fix it</div>
          <ol className="mt-2 max-w-[60ch] list-decimal space-y-2 pl-5 text-ink">
            {cmsSteps.map((step, index) => <li key={`${step}-${index}`} className="pl-1 leading-relaxed">{step}</li>)}
          </ol>

          {reportedCount > 0 ? (
            <>
              <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
                  Affected URLs <span className="font-normal tabular-nums">{availableCount}{reportedCount > availableCount ? ` of ${reportedCount}` : ""}</span>
                </div>
                {availableCount > 0 ? (
                  <div className="flex flex-wrap items-center gap-3 text-[12px]">
                    <button type="button" onClick={copyAffectedUrls} className="flex items-center gap-1.5 text-ink-muted transition-colors hover:text-ink">
                      <Copy className="h-3.5 w-3.5" />
                      {copied ? "Copied" : "Copy all"}
                    </button>
                    <button type="button" onClick={downloadAffectedUrls} className="flex items-center gap-1.5 text-ink-muted transition-colors hover:text-ink">
                      <Download className="h-3.5 w-3.5" />
                      Download CSV
                    </button>
                  </div>
                ) : null}
              </div>

              {reportedCount > availableCount ? (
                <p className="mt-2 max-w-[60ch] rounded-md bg-warnink/[0.07] px-3 py-2 text-[12.5px] leading-relaxed text-ink-muted">
                  This saved record contains {availableCount} of {reportedCount} flagged URLs. Run a fresh scan after this update is published to capture the complete list.
                </p>
              ) : null}

              {item.excludedEvidenceCount > 0 ? (
                <p className="mt-2 max-w-[60ch] text-[12.5px] text-ink-faint">
                  {item.excludedEvidenceCount} non-HTML or system URL{item.excludedEvidenceCount === 1 ? " was" : "s were"} excluded from this customer-facing list.
                </p>
              ) : null}

              {shownPages.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {shownPages.map((page, index) => (
                    <AffectedPage key={`${page}-${index}`} page={page} websiteUrl={item.websiteUrl} index={index} />
                  ))}
                  {extraCount > 0 ? (
                    <button type="button" onClick={() => setShowAllPages(true)} className="mt-1 text-[13px] font-medium text-ink underline decoration-hairline underline-offset-4">
                      Show all {availableCount} URLs
                    </button>
                  ) : null}
                  {showAllPages && availableCount > 8 ? (
                    <button type="button" onClick={() => setShowAllPages(false)} className="mt-1 text-[13px] text-ink-muted underline decoration-hairline underline-offset-4">
                      Show fewer URLs
                    </button>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : null}

          <button
            type="button"
            onClick={onDone}
            className="mt-6 rounded-full border border-hairline px-4 py-1.5 text-[13px] font-medium text-ink transition-colors hover:border-good/25 hover:bg-good/[0.07] hover:text-good focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Mark as done
          </button>
        </div>
      ) : null}
    </div>
  );
}''',
)

replace_between(
    fixlist_path,
    "function AffectedPage({ page }) {\n",
    "function ScanDebugPanel({ debugData, onRefresh, onClear }) {\n",
    r'''function AffectedPage({ page, websiteUrl, index }) {
  const resolvedPage = toAbsolutePageUrl(page, websiteUrl);
  const label = formatPageLabel(resolvedPage);
  const path = formatPagePath(resolvedPage);
  const showPath = cleanString(path) !== cleanString(label);

  return (
    <div className="flex items-start gap-2 rounded-md border border-hairline-soft px-2.5 py-2 text-[13px] tabular-nums">
      <span className="mt-0.5 w-5 shrink-0 text-right text-[11px] text-ink-faint">{index + 1}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{label}</p>
        {showPath ? <p className="break-all text-ink-faint">{path}</p> : null}
      </div>
      {isFullUrl(resolvedPage) ? (
        <a href={resolvedPage} target="_blank" rel="noreferrer" className="shrink-0 p-1 text-ink-faint transition-colors hover:text-ink" aria-label="Open page">
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      ) : null}
    </div>
  );
}

function normalizeAffectedPageList(values) {
  return unique((values || []).map(String).filter(isUsableAffectedPageUrl));
}

function isUsableAffectedPageUrl(value) {
  const raw = String(value || "").trim();
  if (!raw || /^(?:mailto|tel|javascript|data):/i.test(raw)) return false;
  let pathname = raw;
  try {
    pathname = new URL(raw, "https://fixlist.invalid").pathname || "/";
  } catch {}
  if (/^\/cdn-cgi\//i.test(pathname)) return false;
  if (/\.(?:avif|bmp|css|csv|doc|docx|eot|gif|ico|jpe?g|js|json|map|mjs|mp3|mp4|mpeg|mov|ogg|otf|pdf|png|ppt|pptx|svg|tiff?|ttf|wav|webm|webp|woff2?|xls|xlsx|xml|zip)$/i.test(pathname)) return false;
  return raw.startsWith("/") || /^https?:\/\//i.test(raw);
}

function toAbsolutePageUrl(page, websiteUrl) {
  const raw = String(page || "").trim();
  if (!raw) return "";
  if (isFullUrl(raw)) return raw;
  try {
    return new URL(raw, websiteUrl || "https://fixlist.invalid").toString();
  } catch {
    return raw;
  }
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function downloadTextFile(content, filename, type) {
  const blob = new Blob([content], { type });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}''',
)

replace_between(
    fixlist_path,
    "function normalizeRecommendation(item = {}, scanRecord = {}) {\n",
    "function extractRecommendationEvidence(item = {}, scanRecord = {}) {\n",
    r'''function normalizeRecommendation(item = {}, scanRecord = {}) {
  const legacyBlocked429 = shouldUseLegacyRateLimitPresentation(scanRecord, item);
  const evidence = legacyBlocked429 ? extractRecommendationEvidence(item, scanRecord) : {};
  const priority = legacyBlocked429 ? blockedPriority(item, evidence) : normalizePriority(item.priority);
  const category = String(item.category || "other").toLowerCase();
  const rawAffectedPages = unique(firstArray([item.affected_pages, item.pages, item.page_urls]).map(String));
  const fallbackPage = item.page_url || item.url || rawAffectedPages[0] || "";
  const combinedPages = unique([...rawAffectedPages, ...(fallbackPage ? [String(fallbackPage)] : [])]);
  const affectedPages = normalizeAffectedPageList(combinedPages);
  const bucket = legacyBlocked429 ? "needs_developer" : getIssueBucket(item);
  const customerCategory = legacyBlocked429 ? "Scan coverage" : item.customer_category || CATEGORY_LABELS[category] || humanize(category || "Website improvement");
  const title = legacyBlocked429 ? build429Title(evidence) : cleanString(item.issue_title || item.title || item.name) || buildSpecificTitle(item);
  const explanation = legacyBlocked429 ? build429Explanation(evidence) : cleanString(item.plain_english_explanation || item.plain_english_summary || item.explanation || item.description || item.summary || item.recommendation) || buildSpecificExplanation(item);
  const whyItMatters = legacyBlocked429 ? build429Why(evidence) : cleanString(item.why_it_matters || item.impact || item.reason) || buildSpecificWhy(item);
  const recommendation = legacyBlocked429 ? build429Recommendation(evidence) : cleanString(item.simple_next_step || item.recommended_value || item.recommendation || item.suggested_fix || item.ai_recommendation) || "Review the affected page and make the recommended update.";
  const needsHelp = bucket === "needs_developer";

  return {
    id: item.id || item.fix_id || stableId(`${fallbackPage}|${category}|${title}`),
    original: item,
    rule: cleanString(item.rule || item.issue_type),
    category,
    priority,
    bucket,
    customerCategory,
    title,
    explanation,
    whyItMatters,
    recommendation,
    affectedPages,
    sourcePages: normalizeAffectedPageList(firstArray([item.source_pages, item.evidence?.source_pages])),
    pageCount: Math.max(Number(item.page_count || 0), affectedPages.length),
    excludedEvidenceCount: Math.max(0, combinedPages.length - affectedPages.length),
    websiteUrl: cleanString(scanRecord?.website_url || scanRecord?.raw?.scanner?.website_url),
    templateFamily: cleanString(item.page_template_family),
    currentValue: legacyBlocked429 ? "HTTP 429 — crawler was rate-limited or blocked" : cleanString(item.current_value || item.current || item.detected_value),
    pageType: legacyBlocked429 && evidence.scopeRelationship === "sibling_sous_dossier" ? "Sibling sous-dossier" : cleanString(item.page_type || item.page_value_label || item.business_importance),
    defectClass: legacyBlocked429 ? "Rate-limit / crawler access" : cleanString(item.primary_defect_class || item.meta_regeneration_gate),
    pageValueLabel: legacyBlocked429 ? evidence.businessValueLabel : cleanString(item.page_value_label),
    businessImportance: legacyBlocked429 ? evidence.businessImportance : cleanString(item.business_importance),
    metaGate: cleanString(item.meta_regeneration_gate),
    scopeRelationship: legacyBlocked429 ? evidence.scopeRelationship : cleanString(item.scope_relationship),
    pageScope: cleanString(item.page_scope),
    evidenceStatus: cleanString(item.evidence_status || item.verification_state),
    needsHelp,
    generalSteps: legacyBlocked429 ? build429Steps(evidence) : buildGeneralSteps(item, recommendation, needsHelp),
  };
}''',
)

replace_between(
    fixlist_path,
    "function buildGeneralSteps(item = {}, recommendation, needsHelp) {\n",
    "function buildEvidenceItems(recommendation) {\n",
    r'''function buildGeneralSteps(item = {}, recommendation, needsHelp) {
  const existing = firstArray([item.what_to_do_steps, item.what_to_do, item.fix_steps, item.general_steps, item.next_steps, item.steps, item.action_steps]);
  if (existing.length > 0) return existing.map(String).slice(0, 6);
  if (needsHelp) return ["Share this item and its affected-URL export with your web person.", "Ask them to apply the rule-specific change across every affected URL.", "Publish the fix and run FixList again."];

  const category = String(item.category || "").toLowerCase();
  if (category === "meta_title") return ["Open the affected page in your CMS.", "Write a shorter title that names the specific page, service, product, or tool.", "Put the most important phrase near the beginning and keep the brand at the end.", "Publish and run FixList again."];
  if (category === "meta_description") return ["Open the affected page's SEO settings.", "Write one concise description that says what the visitor can do on this page.", "Mention the main benefit or next step, not generic marketing copy.", "Publish and run FixList again."];
  if (category === "schema") return ["Choose the right schema type for the page, such as Organization, LocalBusiness, Product, FAQ, or Breadcrumb.", "Add the schema through your CMS, SEO plugin, theme, or developer.", "Validate the page with a structured data checker."];
  if (category === "canonical") return ["Open the affected page or template.", "Set the canonical URL to the clean official version of the page.", "Check that duplicate, filter, and tracking URLs point back to the official version."];
  return ["Open the affected page or shared template.", recommendation, "Publish the change and run FixList again."];
}

function getCmsSteps(cms, recommendation) {
  if (isBlocked429(recommendation.original)) {
    return [
      "Do not edit page copy first. This is a server, CDN, firewall, or bot-protection check.",
      "Use Copy all or Download CSV under Affected URLs and send the complete list to your web person.",
      "Ask them to check access logs for HTTP 429 or challenge responses on those URLs.",
      "Confirm whether Googlebot and normal users can access the pages, adjust rules only when legitimate access is blocked, then rescan.",
    ];
  }

  const specificSteps = getRuleSpecificSteps(recommendation);
  if (specificSteps.length > 0) return [getCmsOpeningStep(cms, recommendation), ...specificSteps].slice(0, 6);

  const existing = Array.isArray(recommendation.generalSteps) ? recommendation.generalSteps.filter(Boolean) : [];
  if (existing.length > 0) return [getCmsOpeningStep(cms, recommendation), ...existing].slice(0, 6);
  return [getCmsOpeningStep(cms, recommendation), recommendation.recommendation, "Publish the update and run FixList again to verify the issue is gone."];
}

function getRuleSpecificSteps(recommendation) {
  const rule = String(recommendation.rule || recommendation.original?.rule || "").toLowerCase();
  const category = String(recommendation.category || recommendation.original?.category || "").toLowerCase();

  if (rule === "internal_link_redirect") return [
    "Use Copy all or Download CSV under Affected URLs so none of the flagged links are missed.",
    "Search your CMS, navigation, templates, and codebase for each old URL and replace it with the final destination URL shown by the redirect evidence.",
    "Publish the changes, clear any site or CDN cache, and test a representative URL from each affected page family.",
    "Run FixList again; the internal-link redirect count should fall to zero.",
  ];
  if (rule === "sitemap_redirect") return [
    "Export the complete affected-URL list below.",
    "Replace every redirecting sitemap entry with the final 200-status canonical URL; do not leave the old URL in the XML sitemap.",
    "Regenerate the sitemap, open it directly to confirm the old URLs are gone, and resubmit it in Google Search Console.",
    "Run FixList again to verify no sitemap entries redirect.",
  ];
  if (rule === "sitemap_canonicalized_url") return [
    "Export the affected URLs below and identify the canonical destination for each one.",
    "Remove each non-preferred URL from the sitemap and add only its final self-canonical, indexable URL.",
    "Regenerate and resubmit the sitemap, then verify a sample in page source and Google Search Console.",
    "Run FixList again to confirm the conflict is resolved.",
  ];
  if (rule === "sitemap_indexability_conflict") return [
    "Export the full affected-URL list below.",
    "For each URL, choose one outcome: remove it from the sitemap if it should stay noindexed or blocked, or make it crawlable and indexable if it should rank.",
    "Regenerate the sitemap and confirm it contains only preferred, indexable URLs.",
    "Run FixList again to verify the sitemap and indexability settings agree.",
  ];
  if (rule === "redirect_chain") return [
    "Export the complete URL list and inspect the redirect path for each affected URL.",
    "Change the first redirect, internal links, and sitemap entries to point directly to the final destination, removing intermediate hops.",
    "Clear caches and verify each affected URL reaches the final page in no more than one redirect.",
    "Run FixList again to confirm the chains are gone.",
  ];
  if (rule === "redirect_destination_noindex") return [
    "Export every affected URL and review the destination page for each redirect.",
    "If the destination should rank, remove its noindex directive. If it should not rank, redirect to a relevant indexable page or remove the source link or sitemap entry.",
    "Verify the final destination returns 200, is crawlable, and has the intended indexability setting.",
    "Run FixList again to confirm the conflicting redirects are resolved.",
  ];
  if (/redirect_destination_(?:failed|blocked)/.test(rule)) return [
    "Export the full affected-URL list and test each redirect destination directly.",
    "Restore the intended destination or update the redirect to the closest relevant live, crawlable page.",
    "Update internal links and sitemap entries so they also point directly to the working destination.",
    "Run FixList again after deployment to verify every destination is available.",
  ];
  if (/broken|404|410/.test(rule) || category === "404_error") return [
    "Export the affected URLs and decide whether each page should be restored, redirected, or removed.",
    "Restore pages that should exist; otherwise add a 301 redirect to the closest relevant live page.",
    "Update or remove every internal link and sitemap entry that still references the broken URL.",
    "Test the URLs directly, then run FixList again.",
  ];
  if (/canonical/.test(rule) || category === "canonical") return [
    "Use the URL list below to identify whether this is one shared-template problem or a small number of page-specific settings.",
    "Add or correct one self-referencing canonical tag per public page using its clean final URL.",
    "Inspect rendered page source on representative URLs from every affected family and confirm exactly one correct canonical is present.",
    "Publish and run FixList again.",
  ];
  if (/missing_meta_description|empty_meta_description|malformed_meta_description/.test(rule) || category === "meta_description") return [
    "Export the affected URLs and group them by page template or CMS collection.",
    "Add a page-specific description field or repair the shared template so every affected page outputs one non-empty, plain-text meta description.",
    "Open representative page source from each group and confirm the description is present once and contains the expected text.",
    "Publish and run FixList again.",
  ];
  if (/title/.test(rule) || category === "meta_title") return [
    "Export the affected URLs and group pages that share the same title template.",
    "Update the page field or shared title template so each indexable page has a specific title describing its topic or offer.",
    "Check representative page source from each family and confirm the title is unique, clear, and not cut off.",
    "Publish and run FixList again.",
  ];
  if (/image_alt|missing_alt|alt_text/.test(rule) || category === "image_alt_text" || category === "alt_text") return [
    "Export the affected URLs and open one representative page from each page family.",
    "Update the CMS image field or shared image component so meaningful images receive short, specific alt text; keep decorative images empty.",
    "Verify several affected pages in rendered HTML to confirm the template change applied consistently.",
    "Publish and run FixList again.",
  ];
  if (/missing_h1|multiple_h1/.test(rule) || category === "thin_content") return [
    "Open a representative affected page and locate the shared heading field or template.",
    rule.includes("multiple") ? "Keep the main page title as the only H1 and change supporting headings to H2 or H3 without changing their visual style." : "Add one clear H1 that describes the page's main topic; keep supporting sections as H2 or H3.",
    "Check representative pages from every affected family, publish the change, and run FixList again.",
  ];
  if (/schema/.test(rule) || category === "schema") return [
    "Choose the schema type that matches the page, such as Organization, LocalBusiness, Product, FAQ, or BreadcrumbList.",
    "Implement it in the shared template, CMS plugin, or page settings using values that are visible and accurate on the page.",
    "Validate representative affected URLs with a structured-data testing tool, fix errors, then publish and rescan.",
  ];
  return [];
}

function getCmsOpeningStep(cms, recommendation) {
  const repeated = Number(recommendation.pageCount || 0) > 1 || ["family", "cross_cutting", "sitewide"].includes(recommendation.pageScope);
  const label = CMS_OPTIONS.find((option) => option.value === cms)?.label || "your website editor";
  if (recommendation.needsHelp) return `Open ${label} with your web person and ${repeated ? "locate the shared template, navigation, sitemap, or routing rule behind this group" : "locate the setting or code responsible for this URL"}.`;
  return `Open ${label} and ${repeated ? "locate the shared template or collection used by these pages" : "open the affected page's SEO or content settings"}.`;
}''',
)

scan_form_path = "src/components/scan/ScanWebsiteForm.jsx"
replace_once(
    scan_form_path,
    '''      mergedFinal = mergeScanAndAiReview({ scanData, aiData, websiteUrl: normalizedUrl, businessName: trimmedBusinessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix, scanId, scanRunId: scanRunHandle?.id || "" });
      saveScanForDashboard(mergedFinal, scanId);
      const durableRecord = normalizeScanRecordForStorage(mergedFinal);
      await completeScanRun(scanRunHandle, durableRecord).catch(() => null);''',
    '''      mergedFinal = mergeScanAndAiReview({ scanData, aiData, websiteUrl: normalizedUrl, businessName: trimmedBusinessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix, scanId, scanRunId: scanRunHandle?.id || "" });
      const durableRecord = normalizeScanRecordForStorage(mergedFinal);
      const fixListId = await completeScanRun(scanRunHandle, durableRecord).catch(() => null);
      if (fixListId) mergedFinal = { ...mergedFinal, fix_list_id: fixListId };
      saveScanForDashboard(mergedFinal, scanId);''',
)
replace_once(
    scan_form_path,
    'meta_description: clampText(page.meta_description || "", 240), h1:',
    'meta_description: clampText(page.meta_description || "", 240), meta_description_state: page.meta_description_state || "", metadata_evidence_version: page.metadata_evidence_version || "", title_evidence_version: page.title_evidence_version || "", title_evidence_context: page.title_evidence_context || {}, h1:',
)

model_path = "src/lib/scanRunModel.js"
replace_once(
    model_path,
    '    affected_pages: toArr(fix.affected_pages).map(toStr).slice(0, 50),\n    source_pages: toArr(fix.source_pages).map(toStr).slice(0, 50),',
    '    affected_pages: toArr(fix.affected_pages).map(toStr).slice(0, 150),\n    source_pages: toArr(fix.source_pages).map(toStr).slice(0, 150),\n    page_count: Number(fix.page_count || toArr(fix.affected_pages).length || 0),\n    family_breakdown: fix.family_breakdown && typeof fix.family_breakdown === "object" ? fix.family_breakdown : {},\n    representative_pages_by_family: fix.representative_pages_by_family && typeof fix.representative_pages_by_family === "object" ? fix.representative_pages_by_family : {},\n    what_to_do_steps: toArr(fix.what_to_do_steps || fix.what_to_do || fix.fix_steps).map(toStr).slice(0, 8),',
)

entity_path = ROOT / "base44/entities/FixItem.jsonc"
entity = json.loads(entity_path.read_text(encoding="utf-8"))
properties = entity["properties"]
properties.setdefault("page_count", {"type": "number", "default": 0})
properties.setdefault("family_breakdown", {"type": "object", "additionalProperties": True, "default": {}})
properties.setdefault("representative_pages_by_family", {"type": "object", "additionalProperties": True, "default": {}})
properties.setdefault("what_to_do_steps", {"type": "array", "items": {"type": "string"}, "default": []})
entity_path.write_text(json.dumps(entity, indent=2) + "\n", encoding="utf-8")

test_path = ROOT / "tests/frontend/fixListEvidenceUx.test.mjs"
test_path.write_text(r'''import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildFixItemFields } from "../../src/lib/scanRunModel.js";

const fixListSource = readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const scanFormSource = readFileSync(new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url), "utf8");
const fixItemEntity = JSON.parse(readFileSync(new URL("../../base44/entities/FixItem.jsonc", import.meta.url), "utf8"));

test("FixList exposes the complete affected URL list with copy and CSV controls", () => {
  assert.match(fixListSource, /Affected URLs/);
  assert.match(fixListSource, /Show all \{availableCount\} URLs/);
  assert.match(fixListSource, /Copy all/);
  assert.match(fixListSource, /Download CSV/);
  assert.match(fixListSource, /affected_url/);
});

test("FixList instructions are action-oriented and rule specific", () => {
  assert.match(fixListSource, /How to fix it/);
  assert.match(fixListSource, /rule === "internal_link_redirect"/);
  assert.match(fixListSource, /rule === "sitemap_redirect"/);
  assert.match(fixListSource, /rule === "redirect_chain"/);
  assert.match(fixListSource, /redirect_destination_noindex/);
  assert.match(fixListSource, /Run FixList again/);
});

test("customer-facing URL evidence excludes obvious assets and system routes", () => {
  assert.match(fixListSource, /\\/cdn-cgi\\//);
  assert.match(fixListSource, /pdf\|png/);
  assert.match(fixListSource, /non-HTML or system URL/);
});

test("durable FixItems preserve the full 150-page crawl evidence and instructions", () => {
  const affected = Array.from({ length: 150 }, (_, index) => `/page-${index + 1}`);
  const fields = buildFixItemFields({
    issue_title: "Update internal links",
    rule: "internal_link_redirect",
    affected_pages: affected,
    page_count: 150,
    what_to_do_steps: ["Export URLs", "Update links", "Verify"],
    family_breakdown: { standard: 120, legal_info: 30 },
    representative_pages_by_family: { standard: ["/page-1"], legal_info: ["/page-121"] },
  }, { scanRunId: "run_1" });
  assert.equal(fields.affected_pages.length, 150);
  assert.equal(fields.page_count, 150);
  assert.deepEqual(fields.what_to_do_steps, ["Export URLs", "Update links", "Verify"]);
  assert.equal(fields.family_breakdown.standard, 120);
});

test("FixItem entity stores URL counts, family evidence, and fix steps", () => {
  for (const field of ["page_count", "family_breakdown", "representative_pages_by_family", "what_to_do_steps"]) {
    assert.ok(fixItemEntity.properties[field], `FixItem missing ${field}`);
  }
});

test("returned durable fix_list_id is written into the browser scan record", () => {
  assert.match(scanFormSource, /const fixListId = await completeScanRun/);
  assert.match(scanFormSource, /fix_list_id: fixListId/);
  assert.match(scanFormSource, /meta_description_state/);
  assert.match(scanFormSource, /metadata_evidence_version/);
  assert.match(scanFormSource, /title_evidence_version/);
});
''', encoding="utf-8")

print("Applied FixList full URL evidence and instruction-clarity patch.")
