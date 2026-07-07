import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Bug,
  CheckCircle2,
  Copy,
  Download,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { base44 } from "@/api/base44Client";

const ADVANCED_SCANNER_FUNCTION = "runAdvancedScan";
const AI_REVIEW_FUNCTION = "aiReviewScan";

const DASHBOARD_LAST_SCAN_KEY = "seo_autopilot:last_scan";
const DASHBOARD_HISTORY_KEY = "seo_autopilot:scan_history";
const LEGACY_LAST_SCAN_KEY = "SEO_AUTOPILOT_LAST_SCAN";
const LEGACY_HISTORY_KEY = "SEO_AUTOPILOT_SCAN_HISTORY";
const ACTIVE_SCAN_URL_KEY = "seo_autopilot:active_scan_url";
const ACTIVE_SCAN_STARTED_AT_KEY = "seo_autopilot:active_scan_started_at";
const SCAN_DEBUG_KEY = "seo_autopilot:scan_debug";

const SCAN_MODES = [
  { value: "quick", label: "Quick check", description: "Fast first scan. Up to 40 pages." },
  { value: "deep", label: "Standard", description: "Right for most sites. Up to 85 pages." },
  { value: "advanced", label: "Full site", description: "Larger scan. Up to 150 pages." },
];

const CMS_OPTIONS = [
  { value: "wordpress", label: "WordPress" },
  { value: "squarespace", label: "Squarespace" },
  { value: "wix", label: "Wix" },
  { value: "shopify", label: "Shopify" },
  { value: "webflow", label: "Webflow" },
  { value: "framer", label: "Framer" },
  { value: "godaddy", label: "GoDaddy" },
  { value: "joomla", label: "Joomla" },
  { value: "custom", label: "Custom / Not sure" },
];

const LOW_VALUE_PAGE_PATTERNS = ["/actualites", "/news", "/blog", "/archive", "/archives", "/tag/", "/tags/", "/author/", "/feed", "/rss", "/page/", "?page=", "&page=", "?p=", "&p=", "?tag=", "&tag="];
const MONEY_PAGE_PATTERNS = ["devis", "quote", "pricing", "tarif", "contact", "booking", "reservation", "checkout", "ticket", "voucher", "pass", "show", "listing", "product", "produit", "collection", "category", "simulation", "simulateur", "calcul", "calculator", "comparateur", "demo", "signup", "energie", "énergie", "electricite", "électricité", "gaz", "fournisseur"];
const TEMPLATE_RULES = new Set(["client_rendering", "js_rendering", "canonical_missing", "canonical_to_other_url", "schema", "missing_h1", "image_alt_text", "missing_meta_description", "route_boundary_candidate_indexable", "internal_route_indexable"]);

export default function ScanWebsiteForm({ project = null, saving = false }) {
  const navigate = useNavigate();
  const [websiteUrl, setWebsiteUrl] = useState(project?.website_url || "");
  const [businessName, setBusinessName] = useState(project?.business_name || "");
  const [cmsPlatform, setCmsPlatform] = useState(normalizeCmsValue(project?.cms_platform || "custom"));
  const [keywordsText, setKeywordsText] = useState(Array.isArray(project?.important_keywords) ? project.important_keywords.join("\n") : "");
  const [scanMode, setScanMode] = useState(project?.scan_mode || "quick");
  const [optionalOpen, setOptionalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeStep, setActiveStep] = useState("");
  const [error, setError] = useState("");
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugData, setDebugData] = useState(() => readScanDebugData());
  const [debugCopied, setDebugCopied] = useState(false);

  const isLoading = submitting || saving;
  const cleanedKeywords = useMemo(() => splitLines(keywordsText), [keywordsText]);
  const selectedCms = CMS_OPTIONS.find((item) => item.value === cmsPlatform);

  function refreshDebugData() {
    setDebugData(readScanDebugData());
  }

  function clearDebugScanData() {
    clearAllDashboardScanData();
    refreshDebugData();
  }

  async function copyDebugData() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(readScanDebugData(), null, 2));
      setDebugCopied(true);
      window.setTimeout(() => setDebugCopied(false), 1500);
    } catch (copyError) {
      console.warn("Could not copy debug data.", copyError);
    }
  }

  function downloadDebugData() {
    const snapshot = readScanDebugData();
    const website = snapshot?.parsed?.[DASHBOARD_LAST_SCAN_KEY]?.website_url || snapshot?.parsed?.[LEGACY_LAST_SCAN_KEY]?.website_url || websiteUrl || "fixlist";
    const host = safeHostname(website) || "fixlist";
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `fixlist-debug-${host}-${timestamp}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    const normalizedUrl = normalizeWebsiteUrl(websiteUrl);
    const requestedPathPrefix = getRequestedPathPrefix(normalizedUrl);
    const trimmedBusinessName = businessName.trim();
    const cmsName = selectedCms?.label || "Custom / Not sure";
    if (!normalizedUrl) { setError("Enter a valid website URL."); return; }
    if (!trimmedBusinessName) { setError("Enter the business or website name."); return; }

    let scanData = null;
    let aiData = null;
    let mergedFinal = null;
    setSubmitting(true);
    clearPreviousDashboardScan(normalizedUrl);
    writeScanDebug({ status: "running", stage: "scan_started", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix });
    refreshDebugData();

    try {
      const safeScanBudget = getSafeScanBudget(scanMode);
      setActiveStep("Reading your pages");
      const scanPayload = {
        website_url: normalizedUrl,
        requested_start_url: normalizedUrl,
        crawl_path_prefix: requestedPathPrefix,
        strict_path_prefix: true,
        clear_previous_scan: true,
        business_name: trimmedBusinessName,
        cms_platform: cmsPlatform,
        cms_name: cmsName,
        important_keywords: cleanedKeywords,
        competitor_urls: [],
        scan_mode: scanMode,
        enable_screaming_frog_lite: true,
        force_internal_crawl: true,
        respect_robots_txt: false,
        max_pages: safeScanBudget.max_pages,
        max_competitors: 0,
        max_browser_render_attempts: safeScanBudget.max_browser_render_attempts,
        crawl_timeout_ms: safeScanBudget.crawl_timeout_ms,
        source: "scan_website_page",
        requested_at: new Date().toISOString(),
      };
      writeScanDebug({ status: "running", stage: "scanner_request_started", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, payload_summary: { max_pages: scanPayload.max_pages, max_competitors: 0, max_browser_render_attempts: scanPayload.max_browser_render_attempts, crawl_timeout_ms: scanPayload.crawl_timeout_ms, keyword_count: scanPayload.important_keywords.length } });
      refreshDebugData();

      const scannerResponse = await callBase44Function(ADVANCED_SCANNER_FUNCTION, scanPayload);
      scanData = normalizeFunctionResponse(scannerResponse);
      writeScanDebug({ status: "running", stage: "scanner_complete", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData) });
      refreshDebugData();
      if (scanData?.success === false || scanData?.error) throw new Error(scanData.error || "Website scan failed.");

      setActiveStep("Checking SEO issues");
      try {
        const aiPayload = buildAiReviewPayload({ scanData, businessName: trimmedBusinessName, websiteUrl: normalizedUrl, cmsPlatform, cmsName, cleanedKeywords, scanMode, requestedPathPrefix });
        writeScanDebug({ status: "running", stage: "ai_review_request_started", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_payload_summary: { pages_crawled: aiPayload.scan_coverage?.pages_crawled || 0, pages_found: aiPayload.scan_coverage?.pages_found || 0, sampled_pages_sent_to_ai: aiPayload.scan_coverage?.sampled_pages_sent_to_ai || aiPayload.crawled_pages.length, raw_fixes_count: aiPayload.raw_fixes.length, crawl_policy_source: aiPayload.crawl_policy_source, url_evidence_preserved: Boolean(aiPayload.url_evidence_summary), business_priority_rules_enabled: true, coverage_instruction_enabled: true } });
        refreshDebugData();
        setActiveStep("Writing your FixList");
        const aiResponse = await callBase44Function(AI_REVIEW_FUNCTION, aiPayload);
        aiData = normalizeFunctionResponse(aiResponse);
        writeScanDebug({ status: "running", stage: "ai_review_complete", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_review: slimAiData(aiData) });
        refreshDebugData();
      } catch (aiError) {
        console.warn("AI review was skipped or failed.", aiError);
        writeScanDebug({ status: "running", stage: "ai_review_failed_but_continuing", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_review: slimAiData(aiData), ai_error: aiError?.message || String(aiError) });
        refreshDebugData();
      }

      setActiveStep("Saving your FixList");
      mergedFinal = mergeScanAndAiReview({ scanData, aiData, websiteUrl: normalizedUrl, businessName: trimmedBusinessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix });
      saveScanForDashboard(mergedFinal);
      writeScanDebug({ status: "saved", stage: "dashboard_saved", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, scanner: slimScannerData(scanData), ai_review: slimAiData(aiData), final_record: slimScanRecord(mergedFinal), download_available: true });
      refreshDebugData();
      navigate("/dashboard?scan=complete");
    } catch (err) {
      console.error("Website scan failed.", err);
      writeScanDebug({ status: "failed", stage: "scan_failed", website_url: normalizedUrl, business_name: trimmedBusinessName, cms_platform: cmsPlatform, cms_name: cmsName, scan_mode: scanMode, requested_path_prefix: requestedPathPrefix, error: err?.message || String(err), scanner: slimScannerData(scanData), ai_review: slimAiData(aiData), final_record: slimScanRecord(mergedFinal), download_available: true });
      refreshDebugData();
      setError(err?.message || "The website scan failed. Try Quick check first or check the backend function logs.");
    } finally {
      setActiveStep("");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-indigo-50 p-3 text-indigo-600"><Search className="h-6 w-6" /></div>
            <div>
              <p className="text-sm font-medium text-slate-500">FixList scan</p>
              <h2 className="mt-1 text-2xl font-bold text-slate-950">Create your FixList</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Enter a website URL and we’ll turn the scan into a plain-English list of what to fix, what matters most, and what may need a developer.</p>
              <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600"><ShieldCheck className="h-3.5 w-3.5 text-indigo-600" />Read-only scan — FixList never logs in or changes your website.</div>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={() => { refreshDebugData(); setDebugOpen((value) => !value); }} className="shrink-0"><Bug className="mr-2 h-4 w-4" />{debugOpen ? "Hide debug" : "Show debug"}</Button>
        </div>

        {debugOpen ? (
          <div className="mt-6 rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-bold text-slate-950">Scan debug</h3>
                <p className="mt-1 text-xs text-slate-500">Use Download JSON for large scans that are too big to paste into chat.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={refreshDebugData}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button>
                <Button type="button" variant="outline" onClick={copyDebugData}><Copy className="mr-2 h-4 w-4" />{debugCopied ? "Copied" : "Copy JSON"}</Button>
                <Button type="button" variant="outline" onClick={downloadDebugData}><Download className="mr-2 h-4 w-4" />Download JSON</Button>
                <Button type="button" variant="outline" onClick={clearDebugScanData}><Trash2 className="mr-2 h-4 w-4" />Clear scans</Button>
              </div>
            </div>
            <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
              <pre className="max-h-[420px] overflow-auto p-4 text-xs leading-5 text-slate-100">{JSON.stringify(debugData, null, 2)}</pre>
            </div>
          </div>
        ) : null}

        <div className="mt-6 grid gap-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <div><label className="text-sm font-medium text-slate-700">Website URL</label><Input value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} placeholder="https://www.example.com/" disabled={isLoading} className="mt-2" /></div>
            <div><label className="text-sm font-medium text-slate-700">Business or website name</label><Input value={businessName} onChange={(event) => setBusinessName(event.target.value)} placeholder="Example Business" disabled={isLoading} className="mt-2" /></div>
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">Scan size</label>
            <div className="mt-2 grid gap-3 md:grid-cols-3">
              {SCAN_MODES.map((mode) => {
                const active = scanMode === mode.value;
                return (
                  <button key={mode.value} type="button" disabled={isLoading} onClick={() => setScanMode(mode.value)} className={`rounded-2xl border p-4 text-left transition ${active ? "border-indigo-500 bg-indigo-50 text-slate-950 ring-2 ring-indigo-100" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}>
                    <div className="flex items-center gap-2"><CheckCircle2 className={`h-4 w-4 ${active ? "text-indigo-600" : "text-slate-300"}`} /><span className="font-semibold">{mode.label}</span></div>
                    <p className="mt-2 text-xs leading-5 text-slate-500">{mode.description}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <button type="button" onClick={() => setOptionalOpen((value) => !value)} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-100">{optionalOpen ? "Hide optional settings" : "Optional: personalize your FixList"}</button>

          {optionalOpen ? (
            <div className="grid gap-5 rounded-3xl border border-slate-200 bg-slate-50 p-4 lg:grid-cols-2">
              <div>
                <label className="text-sm font-medium text-slate-700">CMS / website builder</label>
                <select value={cmsPlatform} onChange={(event) => setCmsPlatform(event.target.value)} disabled={isLoading} className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-950 shadow-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50">
                  {CMS_OPTIONS.map((cms) => <option key={cms.value} value={cms.value}>{cms.label}</option>)}
                </select>
                <p className="mt-1 text-xs text-slate-500">We’ll tailor every fix to your CMS — where to click and what to change.</p>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Important keywords</label>
                <textarea value={keywordsText} onChange={(event) => setKeywordsText(event.target.value)} placeholder={"local service\nbest product\nnear me"} disabled={isLoading} rows={4} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50" />
                <p className="mt-1 text-xs text-slate-500">Optional. We’ll check whether your pages clearly target these searches.</p>
              </div>
            </div>
          ) : null}
        </div>

        {error ? <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><div className="flex items-start gap-2"><AlertCircle className="mt-0.5 h-4 w-4" /><span>{error}</span></div></div> : null}
        {isLoading ? <div className="mt-6 rounded-2xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-950"><div className="flex items-center gap-3"><Loader2 className="h-4 w-4 animate-spin" /><span>{activeStep || "Running scan..."}</span></div></div> : null}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button type="submit" disabled={isLoading} className="bg-indigo-600 text-white hover:bg-indigo-700">{isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Building FixList...</> : <><Search className="mr-2 h-4 w-4" />Create FixList</>}</Button>
          <p className="text-xs text-slate-500">Most scans take 1–2 minutes. Start with Quick check, then use Standard or Full site if needed.</p>
        </div>
      </form>
    </div>
  );
}

function buildAiReviewPayload({ scanData, businessName, websiteUrl, cmsPlatform, cmsName, cleanedKeywords, scanMode, requestedPathPrefix }) {
  const crawledPages = getPages(scanData).slice(0, 150);
  const rawFixes = getRecommendations(scanData).slice(0, 140);
  const pagesCrawled = getFirstNumber([scanData?.pages_crawled, scanData?.pages_scanned, scanData?.technical_audit_summary?.pages_crawled, crawledPages.length]);
  const pagesFound = getFirstNumber([scanData?.pages_found, scanData?.pages_discovered, scanData?.technical_audit_summary?.pages_found, pagesCrawled, crawledPages.length]);
  const scanCoverage = { pages_crawled: pagesCrawled, pages_found: pagesFound, sampled_pages_sent_to_ai: crawledPages.length, sampled_findings_sent_to_ai: rawFixes.length, sample_limit: 150 };
  return {
    business_name: businessName,
    website_url: websiteUrl,
    cms_platform: cmsPlatform,
    cms_name: cmsName,
    important_keywords: cleanedKeywords,
    scan_mode: scanMode,
    scan_coverage: scanCoverage,
    coverage_instruction: "Use scan_coverage.pages_crawled as the number of pages reviewed by the scanner. Do not describe sampled_pages_sent_to_ai as the total scan size.",
    ai_review_goal: "Create a customer-friendly FixList that prioritizes business-important pages first. Preserve URL evidence, group template-level problems, and do not treat suspicious crawler artifacts as confirmed broken links.",
    cms_instruction: buildCmsInstruction(cmsPlatform),
    business_priority_instruction: {
      rule: "Prioritize by business importance, not just technical severity.",
      high_priority_pages: ["homepage or scanned section landing page", "booking, checkout, product, listing, category, quote, calculator, comparison, pricing, contact, supplier, tariff, and trust pages", "pages with verified crawler provenance"],
      low_priority_pages: ["old news posts", "month/year archive pages", "blog archives", "tag/archive/feed/pagination pages", "suspicious encoded URLs without source-page proof"],
      evidence_rule: "Use discovered_from, source_pages, link_text_samples, url_confidence, url_evidence_summary, verified_failed_pages, and suspicious_url_artifacts before calling a URL broken.",
      grouping_rule: "Group repeated client rendering, schema, H1, meta, image-alt, 404, 410, 429, and template issues.",
      ownership_rule: "SSR, JavaScript rendering, schema templates, canonicals, redirects, firewall/bot protection, server errors, route boundaries, noindex/indexability, and crawlability belong to your_web_person.",
      requested_path_prefix: requestedPathPrefix || "",
    },
    output_requirements: { keep_language_simple: true, group_similar_issues: true, create_top_priorities: true, include_developer_flags_only_when_needed: true, explain_scan_focus: true, prioritize_money_pages_first: true, demote_low_value_archive_pages: true, preserve_url_evidence_fields: true, do_not_overwrite_developer_owner_with_you: true, use_scan_coverage_for_page_counts: true },
    crawled_pages: crawledPages,
    raw_fixes: rawFixes,
    competitor_results: [],
    discovered_competitors: [],
    crawl_policy: scanData?.crawl_policy || scanData?.technical_audit_summary?.crawl_policy || {},
    crawl_policy_source: scanData?.crawl_policy_source || scanData?.technical_audit_summary?.crawl_policy?.source || "",
    url_evidence_summary: scanData?.url_evidence_summary || scanData?.technical_audit_summary?.url_evidence_summary || {},
    verified_failed_pages: getFirstNumber([scanData?.verified_failed_pages, scanData?.scan_summary?.verified_failed_pages, scanData?.technical_audit_summary?.verified_failed_pages]),
    suspicious_url_artifacts: getFirstNumber([scanData?.suspicious_url_artifacts, scanData?.scan_summary?.suspicious_url_artifacts, scanData?.technical_audit_summary?.suspicious_url_artifacts]),
    important_page_patterns: unique([requestedPathPrefix || "", ...MONEY_PAGE_PATTERNS]).slice(0, 60),
    deprioritized_page_patterns: unique([...LOW_VALUE_PAGE_PATTERNS, "suspicious encoded URLs", "crawler artifacts", "tag/archive/feed/pagination"]).slice(0, 50),
    crawl_warnings: firstArray([scanData?.crawl_warnings]),
    technical_audit_summary: scanData?.technical_audit_summary || {},
    scan_summary: scanData?.scan_summary || scanData?.site_summary || {},
  };
}

function mergeScanAndAiReview({ scanData, aiData, websiteUrl, businessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix }) {
  const pages = getPages(scanData).slice(0, 150).map(slimPage);
  const scannerFixes = getRecommendations(scanData);
  const aiFixes = getRecommendations(aiData);
  const finalFixes = groupAndSortFixes((aiFixes.length > 0 ? aiFixes : scannerFixes).map(slimFix), { requestedPathPrefix }).slice(0, 120);
  const healthScore = getFirstNumber([aiData?.health_score, aiData?.seo_score, aiData?.website_health_report?.health_score, aiData?.scan_summary?.health_score, scanData?.health_score, scanData?.seo_score, scanData?.scan_summary?.score, scanData?.scan_summary?.health_score]);
  const pagesCrawled = getFirstNumber([scanData?.pages_crawled, scanData?.pages_scanned, scanData?.technical_audit_summary?.pages_crawled, pages.length]);
  const pagesFound = getFirstNumber([scanData?.pages_found, scanData?.pages_discovered, scanData?.technical_audit_summary?.pages_found, pagesCrawled, pages.length]);
  const crawlPolicy = scanData?.crawl_policy || scanData?.technical_audit_summary?.crawl_policy || {};
  const technicalSummary = slimTechnicalSummary(scanData?.technical_audit_summary || {}, scanData);
  const summaryText = normalizeCoverageSummary(aiData?.customer_summary || aiData?.plain_english_summary || aiData?.summary || aiData?.website_health_report?.overall_explanation || scanData?.scan_summary?.plain_english_summary || buildFallbackSummary({ healthScore, pagesCrawled, finalFixes, cmsName }), pagesCrawled);
  const siteFingerprint = normalizeSiteFingerprint(aiData?.site_fingerprint || aiData?.scan_summary?.site_fingerprint || {}, pages);

  return {
    id: `scan_${Date.now()}`,
    created_at: new Date().toISOString(),
    website_url: websiteUrl,
    website_key: normalizeWebsiteKey(websiteUrl),
    requested_path_prefix: requestedPathPrefix || "",
    business_name: businessName,
    cms_platform: cmsPlatform,
    cms_name: cmsName,
    scan_mode: scanMode,
    health_score: healthScore || 0,
    seo_score: healthScore || 0,
    pages_crawled: pagesCrawled || pages.length || 0,
    pages_found: pagesFound || pages.length || 0,
    customer_summary: summaryText,
    simple_summary: summaryText,
    cms_action_plan: aiData?.cms_action_plan || aiData?.cms_plan || aiData?.implementation_plan || buildCmsActionPlan(cmsPlatform, cmsName, finalFixes),
    top_recommended_actions: buildTopActions({ aiData, finalFixes }).map(slimAction),
    recommendations: finalFixes,
    fixes: finalFixes,
    findings: finalFixes,
    crawled_pages: pages,
    pages,
    scanned_pages: pages,
    scan_summary: slimScanSummary(aiData?.scan_summary || scanData?.scan_summary || {}, healthScore, pagesCrawled, finalFixes, scanData, summaryText),
    site_summary: slimScanSummary(scanData?.site_summary || scanData?.scan_summary || {}, healthScore, pagesCrawled, finalFixes, scanData, summaryText),
    technical_audit_summary: technicalSummary,
    website_health_report: slimHealthReport(aiData?.website_health_report || scanData?.website_health_report || {}, summaryText, healthScore),
    positive_findings: firstArray([aiData?.positive_findings, scanData?.positive_findings, scanData?.site_summary?.positives]).slice(0, 8).map(String),
    health_explanation: aiData?.health_explanation || scanData?.health_explanation || "",
    crawl_policy: crawlPolicy,
    crawl_policy_source: scanData?.crawl_policy_source || crawlPolicy?.source || technicalSummary.crawl_policy_source || "",
    url_evidence_summary: scanData?.url_evidence_summary || technicalSummary.url_evidence_summary || {},
    verified_failed_pages: getFirstNumber([scanData?.verified_failed_pages, scanData?.scan_summary?.verified_failed_pages, technicalSummary.verified_failed_pages]),
    suspicious_url_artifacts: getFirstNumber([scanData?.suspicious_url_artifacts, scanData?.scan_summary?.suspicious_url_artifacts, technicalSummary.suspicious_url_artifacts]),
    crawl_scope: scanData?.crawl_scope || {},
    sitemap_priority_summary: scanData?.sitemap_priority_summary || {},
    important_page_patterns: firstArray([scanData?.important_page_patterns, aiData?.important_page_patterns]).slice(0, 30),
    deprioritized_page_patterns: unique([...firstArray([scanData?.deprioritized_page_patterns, aiData?.deprioritized_page_patterns]), ...LOW_VALUE_PAGE_PATTERNS]).slice(0, 40),
    recommended_followup_scans: firstArray([scanData?.recommended_followup_scans, aiData?.recommended_followup_scans]).slice(0, 10),
    site_fingerprint: siteFingerprint,
    archetype_playbook: aiData?.archetype_playbook || {},
    competitor_result: {},
    competitor_results: [],
    competitor_opportunities: [],
    crawl_warnings: firstArray([scanData?.crawl_warnings, aiData?.crawl_warnings]).slice(0, 10),
    debug: {
      scanner_function: ADVANCED_SCANNER_FUNCTION,
      ai_function: AI_REVIEW_FUNCTION,
      screaming_frog_lite_enabled: true,
      scanner_success: scanData?.success !== false,
      ai_success: aiData?.success === true,
      ai_provider: aiData?.provider || aiData?.ai_provider || aiData?.debug?.provider || "",
      cms_platform: cmsPlatform,
      requested_path_prefix: requestedPathPrefix || "",
      scanner_version: scanData?.version || scanData?.scanner_version || technicalSummary.scanner_version || "",
      ai_scoring_model: aiData?.site_fingerprint?.scoring_model || aiData?.scoring_model || "",
      archetype_label: siteFingerprint?.archetype_label || siteFingerprint?.vertical_label || "",
      crawl_policy_source: scanData?.crawl_policy_source || crawlPolicy?.source || "",
      verified_failed_pages: getFirstNumber([scanData?.verified_failed_pages, scanData?.scan_summary?.verified_failed_pages, technicalSummary.verified_failed_pages]),
      suspicious_url_artifacts: getFirstNumber([scanData?.suspicious_url_artifacts, scanData?.scan_summary?.suspicious_url_artifacts, technicalSummary.suspicious_url_artifacts]),
      saved_as_slim_record: true,
      evidence_fields_preserved: true,
      template_grouping_enabled: true,
      download_json_enabled: true,
      scan_coverage_pages_crawled: pagesCrawled,
      scan_coverage_pages_found: pagesFound,
    },
    raw: { scanner: slimScannerData(scanData), ai_review: slimAiData(aiData) },
  };
}

function getSafeScanBudget(scanMode) {
  if (scanMode === "advanced") return { max_pages: 150, max_browser_render_attempts: 1, crawl_timeout_ms: 90000 };
  if (scanMode === "deep") return { max_pages: 85, max_browser_render_attempts: 1, crawl_timeout_ms: 75000 };
  return { max_pages: 40, max_browser_render_attempts: 1, crawl_timeout_ms: 45000 };
}

async function callBase44Function(functionName, payload) {
  const timeoutMs = functionName === ADVANCED_SCANNER_FUNCTION ? Number(payload?.crawl_timeout_ms || 30000) + 15000 : 70000;
  return await Promise.race([
    callBase44FunctionWithoutTimeout(functionName, payload),
    new Promise((_, reject) => window.setTimeout(() => reject(new Error(`${functionName} did not return within ${Math.round(timeoutMs / 1000)} seconds. The scan may have timed out before saving results.`)), timeoutMs)),
  ]);
}

async function callBase44FunctionWithoutTimeout(functionName, payload) {
  if (base44?.functions?.invoke) return await base44.functions.invoke(functionName, payload);
  if (typeof base44?.functions?.[functionName] === "function") return await base44.functions[functionName](payload);
  throw new Error(`${functionName} failed. No supported Base44 function caller was found.`);
}

function normalizeFunctionResponse(response) {
  if (!response) return {};
  if (response.data?.data) return response.data.data;
  if (response.data?.result) return response.data.result;
  if (response.data) return response.data;
  if (response.result?.data) return response.result.data;
  if (response.result) return response.result;
  if (response.body) return response.body;
  return response;
}

function saveScanForDashboard(scanRecord) {
  try {
    const normalizedRecord = slimScanRecord(normalizeScanRecordForStorage(scanRecord));
    const serialized = JSON.stringify(normalizedRecord);
    [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY].forEach((key) => window.localStorage.setItem(key, serialized));
    [DASHBOARD_HISTORY_KEY, LEGACY_HISTORY_KEY].forEach((key) => {
      const existingRaw = window.localStorage.getItem(key);
      const existing = existingRaw ? JSON.parse(existingRaw) : [];
      const history = Array.isArray(existing) ? existing : [];
      const nextHistory = [normalizedRecord, ...history.filter((item) => item?.website_key !== normalizedRecord.website_key)].slice(0, 8).map(slimScanRecord);
      window.localStorage.setItem(key, JSON.stringify(nextHistory));
    });
    window.localStorage.removeItem(ACTIVE_SCAN_URL_KEY);
    window.localStorage.removeItem(ACTIVE_SCAN_STARTED_AT_KEY);
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (storageError) {
    console.error("Could not save scan for dashboard.", storageError);
    throw new Error("The scan finished, but FixList could not save the summary. Clear scans and try again.");
  }
}

function normalizeScanRecordForStorage(record) {
  const fixes = getRecommendations(record).map(slimFix);
  const pages = getPages(record).map(slimPage);
  const healthScore = getHealthScore(record);
  return { ...record, id: record?.id || `scan_${Date.now()}`, created_at: record?.created_at || new Date().toISOString(), website_url: record?.website_url || "", website_key: normalizeWebsiteKey(record?.website_url || ""), business_name: record?.business_name || "", cms_platform: record?.cms_platform || "custom", cms_name: record?.cms_name || "Custom / Not sure", scan_mode: record?.scan_mode || "quick", health_score: Number(healthScore || 0), seo_score: Number(healthScore || 0), pages_crawled: Number(record?.pages_crawled || pages.length || 0), pages_found: Number(record?.pages_found || pages.length || 0), customer_summary: record?.customer_summary || record?.simple_summary || "", simple_summary: record?.simple_summary || record?.customer_summary || "", recommendations: fixes, fixes, findings: fixes, crawled_pages: pages, pages, scanned_pages: pages };
}

function clearPreviousDashboardScan(activeUrl) {
  try {
    [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY, DASHBOARD_HISTORY_KEY, LEGACY_HISTORY_KEY, SCAN_DEBUG_KEY].forEach((key) => window.localStorage.removeItem(key));
    if (activeUrl) {
      window.localStorage.setItem(ACTIVE_SCAN_URL_KEY, activeUrl);
      window.localStorage.setItem(ACTIVE_SCAN_STARTED_AT_KEY, new Date().toISOString());
    }
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (storageError) {
    console.warn("Could not clear previous dashboard scan.", storageError);
  }
}

function clearAllDashboardScanData() {
  try {
    [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY, DASHBOARD_HISTORY_KEY, LEGACY_HISTORY_KEY, ACTIVE_SCAN_URL_KEY, ACTIVE_SCAN_STARTED_AT_KEY, SCAN_DEBUG_KEY].forEach((key) => window.localStorage.removeItem(key));
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (storageError) {
    console.warn("Could not clear scan data.", storageError);
  }
}

function writeScanDebug(data) {
  try {
    const fullDebug = { ...data, updated_at: new Date().toISOString(), local_storage_keys: { last_scan: DASHBOARD_LAST_SCAN_KEY, history: DASHBOARD_HISTORY_KEY, debug: SCAN_DEBUG_KEY }, download_json_enabled: true };
    window.localStorage.setItem(SCAN_DEBUG_KEY, JSON.stringify(fullDebug));
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (storageError) {
    console.warn("Could not write scan debug data.", storageError);
  }
}

function readScanDebugData() {
  if (typeof window === "undefined") return { raw: {}, parsed: {} };
  const keys = [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY, DASHBOARD_HISTORY_KEY, LEGACY_HISTORY_KEY, ACTIVE_SCAN_URL_KEY, ACTIVE_SCAN_STARTED_AT_KEY, SCAN_DEBUG_KEY];
  const raw = {};
  const parsed = {};
  keys.forEach((key) => {
    const value = window.localStorage.getItem(key);
    raw[key] = value;
    try { parsed[key] = value ? JSON.parse(value) : null; } catch { parsed[key] = value; }
  });
  return { read_at: new Date().toISOString(), raw, parsed };
}

function buildCmsInstruction(cmsPlatform) {
  const instructions = {
    wordpress: "Tailor fixes for WordPress. Mention SEO plugins such as Yoast, Rank Math, or All in One SEO when useful.",
    squarespace: "Tailor fixes for Squarespace. Explain steps using page settings, SEO tab, image settings, redirects, and navigation settings.",
    wix: "Tailor fixes for Wix. Explain steps using Wix SEO settings, page SEO basics, URL slugs, headings, alt text, redirects, and structured data tools.",
    shopify: "Tailor fixes for Shopify. Explain steps for products, collections, pages, theme editor, navigation, image alt text, URL redirects, and SEO fields.",
    webflow: "Tailor fixes for Webflow. Explain steps using page settings, CMS collections, SEO settings, redirects, alt text, and publishing.",
    framer: "Tailor fixes for Framer. Explain steps using page settings, metadata, headings, components, images, and publishing.",
    godaddy: "Tailor fixes for GoDaddy Website Builder. Explain simple steps using page settings, SEO tools, headings, images, and navigation.",
    joomla: "Tailor fixes for Joomla. Explain steps using Articles, Menus, Global Configuration, Metadata Options, SEF URLs, redirects, extensions, templates, headings, image alt text, and structured data extensions where useful.",
    custom: "Tailor fixes for a custom or unknown CMS. Explain which changes can be made by a site editor and which likely need a developer.",
  };
  return instructions[cmsPlatform] || instructions.custom;
}

function buildCmsActionPlan(cmsPlatform, cmsName, fixes) {
  const count = Array.isArray(fixes) ? fixes.length : 0;
  const intro = `This website is marked as ${cmsName}. Start with the highest-impact SEO fixes first, then handle the easier cleanup tasks.`;
  const developerNote = fixes.some((fix) => fix.requires_developer) ? " Some items should go to your web person because they involve rendering, schema, canonicals, redirects, route boundaries, or server/crawl setup." : "";
  return `${intro} There are ${count} recommendations ready for review.${developerNote}`;
}

function slimScannerData(scanner = {}) {
  if (!scanner) return null;
  return { success: scanner.success, version: scanner.version || scanner.scanner_version, website_url: scanner.website_url, scan_mode: scanner.scan_mode, pages_found: scanner.pages_found, pages_crawled: scanner.pages_crawled, queued_remaining: scanner.queued_remaining, health_score: scanner.health_score, seo_score: scanner.seo_score, crawl_policy_source: scanner.crawl_policy_source || scanner.crawl_policy?.source || scanner.technical_audit_summary?.crawl_policy?.source || "", crawl_policy: scanner.crawl_policy || scanner.technical_audit_summary?.crawl_policy || {}, url_evidence_summary: scanner.url_evidence_summary || scanner.technical_audit_summary?.url_evidence_summary || {}, verified_failed_pages: getFirstNumber([scanner.verified_failed_pages, scanner.scan_summary?.verified_failed_pages, scanner.technical_audit_summary?.verified_failed_pages]), suspicious_url_artifacts: getFirstNumber([scanner.suspicious_url_artifacts, scanner.scan_summary?.suspicious_url_artifacts, scanner.technical_audit_summary?.suspicious_url_artifacts]), technical_audit_summary: slimTechnicalSummary(scanner.technical_audit_summary || {}, scanner), crawl_warnings: firstArray([scanner.crawl_warnings]).slice(0, 10), recommendations_count: getRecommendations(scanner).length, pages_preview: getPages(scanner).slice(0, 12).map(slimPage), recommendations_preview: getRecommendations(scanner).slice(0, 18).map(slimFix) };
}

function slimAiData(ai = {}) {
  if (!ai) return null;
  const recommendations = getRecommendations(ai);
  return { success: ai.success, ai_provider: ai.ai_provider || ai.provider || ai.debug?.provider || "", ai_review_warning: ai.ai_review_warning || "", health_score: ai.health_score || ai.seo_score || ai.website_health_report?.health_score || ai.website_health_report?.score || 0, customer_summary: ai.customer_summary || ai.plain_english_summary || ai.summary || ai.website_health_report?.overall_explanation || "", website_health_report: slimHealthReport(ai.website_health_report || {}), site_fingerprint: ai.site_fingerprint || ai.scan_summary?.site_fingerprint || {}, archetype_playbook: ai.archetype_playbook || {}, top_recommended_actions: firstArray([ai.top_recommended_actions, ai.recommended_actions]).slice(0, 5).map((action) => hydrateActionWithFix(action, findSimilarFix(action, recommendations))), recommendations_count: recommendations.length, recommendations_preview: recommendations.slice(0, 18).map(slimFix), ai_rewrites_applied: ai.ai_rewrites_applied || 0 };
}

function slimScanRecord(record = {}) {
  if (!record) return null;
  const recommendations = getRecommendations(record);
  const pages = getPages(record);
  return { ...record, id: record.id || `scan_${Date.now()}`, created_at: record.created_at || new Date().toISOString(), website_url: record.website_url || "", website_key: record.website_key || normalizeWebsiteKey(record.website_url || ""), recommendations: recommendations.slice(0, 120).map(slimFix), fixes: recommendations.slice(0, 120).map(slimFix), findings: recommendations.slice(0, 120).map(slimFix), crawled_pages: pages.slice(0, 150).map(slimPage), pages: pages.slice(0, 150).map(slimPage), scanned_pages: pages.slice(0, 150).map(slimPage), top_recommended_actions: firstArray([record.top_recommended_actions]).slice(0, 5).map((action) => hydrateActionWithFix(action, findSimilarFix(action, recommendations))), debug: { ...(record.debug || {}), download_json_enabled: true } };
}

function slimFix(fix = {}) {
  const affectedPages = firstArray([fix.affected_pages, fix.pages, fix.page_urls]);
  const fallbackPage = fix.page_url || fix.url || affectedPages[0] || "";
  const rule = fix.rule || fix.issue_type || "";
  const category = fix.category || inferCategory(rule, fix);
  const id = fix.id || fix.fix_id || fix.fingerprint || stableId(`${fallbackPage}|${category}|${fix.title || fix.issue_title}`);
  const developerOwned = needsDeveloperOwner({ ...fix, rule, category });
  const title = cleanString(fix.title || fix.issue_title) || defaultTitle(category);
  return { id, fix_id: fix.fix_id || id, rule, category, customer_category: isImageAltTextIssue({ ...fix, rule, category }) ? "Images" : fix.customer_category || friendlyCustomerCategory(category), priority: normalizePriority(fix.priority), difficulty: developerOwned ? "developer" : fix.difficulty || (fix.requires_developer ? "developer" : "easy"), status: developerOwned ? "needs_developer" : fix.status || (fix.requires_developer ? "needs_developer" : fix.can_auto_fix ? "auto_fixed" : "needs_approval"), issue_title: title, title, plain_english_explanation: cleanString(fix.plain_english_explanation || fix.explanation || fix.summary || fix.description) || "This recommendation was found during the website scan.", plain_english_summary: cleanString(fix.plain_english_summary || fix.plain_english_explanation || fix.explanation || ""), why_it_matters: cleanString(fix.why_it_matters || fix.why || fix.impact) || "Improving this can help visitors and search engines understand the website more clearly.", recommendation: cleanString(fix.recommendation || fix.ai_recommendation || fix.recommended_value || fix.suggested_fix) || "Review this recommendation.", recommended_value: cleanString(fix.recommended_value || fix.recommendation || fix.ai_recommendation || fix.suggested_fix) || "Review this recommendation.", simple_next_step: cleanString(fix.simple_next_step || fix.next_step || fix.recommended_value || fix.recommendation) || "Review this item and update the affected page.", page_url: fallbackPage, affected_pages: unique([...(affectedPages || []), ...(fallbackPage ? [fallbackPage] : [])].map(String)).slice(0, 150), source_pages: firstArray([fix.source_pages]).slice(0, 30), link_text_samples: firstArray([fix.link_text_samples]).slice(0, 20), url_confidence: fix.url_confidence || "", url_suspicion_reasons: firstArray([fix.url_suspicion_reasons]).slice(0, 8), current_value: clampText(fix.current_value || fix.current || "", 260), can_auto_fix: Boolean(fix.can_auto_fix), requires_approval: developerOwned ? false : fix.requires_approval !== false, requires_developer: developerOwned || Boolean(fix.requires_developer), who_can_do_this: developerOwned ? "your_web_person" : normalizeOwner(fix.who_can_do_this || "you"), what_to_do: firstArray([fix.what_to_do, fix.what_to_do_steps, fix.fix_steps, fix.steps]).slice(0, 5).map(String), what_to_do_steps: firstArray([fix.what_to_do_steps, fix.what_to_do, fix.fix_steps, fix.steps]).slice(0, 5).map(String), estimated_time: fix.estimated_time || fix.time_estimate || "", time_estimate: fix.time_estimate || fix.estimated_time || "", confidence_score: typeof fix.confidence_score === "number" ? fix.confidence_score : 90, source: fix.source || "", business_importance: fix.business_importance || "standard", is_low_value_page: Boolean(fix.is_low_value_page) || isLowValuePage(fallbackPage), is_important_business_page: Boolean(fix.is_important_business_page) || isImportantBusinessPage(fallbackPage), page_type: fix.page_type || "", page_template_family: fix.page_template_family || classifyTemplateFamily(fallbackPage), primary_defect_class: fix.primary_defect_class || "", meta_rewrite_allowed: Boolean(fix.meta_rewrite_allowed), meta_regeneration_gate: fix.meta_regeneration_gate || "", page_value_score: Number(fix.page_value_score || 0), page_value_label: fix.page_value_label || "", evidence_confidence: Number(fix.evidence_confidence || 0), site_fit_score: Number(fix.site_fit_score || 0), business_impact_score: Number(fix.business_impact_score || 0), reach_score: Number(fix.reach_score || 0), overall_priority_score: Number(fix.overall_priority_score || 0), page_count: Number(fix.page_count || affectedPages.length || 1) };
}

function slimPage(page = {}) {
  return { url: page.url || page.final_url || "", final_url: page.final_url || page.url || "", path: page.path || "", source: page.source || "", discovered_from: firstArray([page.discovered_from]).slice(0, 8), source_pages: firstArray([page.source_pages]).slice(0, 12), link_text_samples: firstArray([page.link_text_samples]).slice(0, 8), url_confidence: page.url_confidence || "", url_suspicion_reasons: firstArray([page.url_suspicion_reasons]).slice(0, 8), route_boundary_candidate: Boolean(page.route_boundary_candidate), route_boundary_type: page.route_boundary_type || "", status_code: Number(page.status_code || 0), fetch_error: page.fetch_error || "", title: clampText(page.title || "", 160), meta_description: clampText(page.meta_description || "", 240), h1: clampText(page.h1 || "", 160), h1_count: Number(page.h1_count || 0), canonical: page.canonical || page.canonical_url || "", canonical_url: page.canonical_url || page.canonical || "", canonical_status: page.canonical_status || "", robots: page.robots || page.robots_meta || "", robots_meta: page.robots_meta || page.robots || "", robots_indexability_status: page.robots_indexability_status || "", word_count: Number(page.word_count || 0), html_size: Number(page.html_size || 0), image_count: Number(page.image_count || 0), image_missing_alt_count: Number(page.image_missing_alt_count || page.missing_alt_image_count || 0), missing_alt_image_count: Number(page.missing_alt_image_count || page.image_missing_alt_count || 0), schema_count: Number(page.schema_count || 0), schema_types: firstArray([page.schema_types]).slice(0, 20), has_schema: Boolean(page.has_schema), internal_link_count: Number(page.internal_link_count || 0), external_link_count: Number(page.external_link_count || 0), indexable: page.indexable !== false, in_sitemap: Boolean(page.in_sitemap), is_scanner_blocked: Boolean(page.is_scanner_blocked), client_rendering_suspected: Boolean(page.client_rendering_suspected), page_template_family: page.page_template_family || classifyTemplateFamily(page.url || page.final_url || ""), estimated_page_intent: page.estimated_page_intent || "", conversion_signals: firstArray([page.conversion_signals]).slice(0, 12), trust_signals: firstArray([page.trust_signals]).slice(0, 12) };
}

function slimAction(action = {}) {
  const developerOwned = needsDeveloperOwner(action);
  return { fix_id: action.fix_id || action.id || "", title: cleanString(action.title || action.issue_title || "Recommended action"), reason: cleanString(action.reason || action.why_it_matters || action.plain_english_summary || ""), priority: normalizeActionPriority(action.priority), plain_english_summary: cleanString(action.plain_english_summary || action.reason || ""), why_it_matters: cleanString(action.why_it_matters || action.reason || ""), what_to_do_steps: firstArray([action.what_to_do_steps, action.what_to_do, action.steps]).slice(0, 5).map(String), who_can_do_this: developerOwned ? "Your web person" : normalizeDisplayOwner(action.who_can_do_this || "You"), time_estimate: action.time_estimate || action.estimated_time || "", affected_pages: firstArray([action.affected_pages]).slice(0, 30) };
}

function slimTechnicalSummary(summary = {}, source = {}) {
  return { ...summary, audit_profile: summary.audit_profile || source?.audit_profile || "", scanner_version: summary.scanner_version || source?.scanner_version || source?.version || "", screaming_frog_lite_enabled: Boolean(summary.screaming_frog_lite_enabled || source?.screaming_frog_lite_enabled), pages_checked: Number(summary.pages_checked || summary.pages_crawled || source?.pages_crawled || 0), pages_crawled: Number(summary.pages_crawled || source?.pages_crawled || 0), pages_found: Number(summary.pages_found || source?.pages_found || 0), failed_pages: Number(summary.failed_pages || 0), verified_failed_pages: Number(summary.verified_failed_pages || source?.verified_failed_pages || source?.scan_summary?.verified_failed_pages || 0), suspicious_url_artifacts: Number(summary.suspicious_url_artifacts || source?.suspicious_url_artifacts || source?.scan_summary?.suspicious_url_artifacts || 0), route_boundary_risk: summary.route_boundary_risk || "", route_boundary_candidates_crawled: Number(summary.route_boundary_candidates_crawled || 0), duplicate_casing_routes: firstArray([summary.duplicate_casing_routes]).slice(0, 20), free_base44_subdomain: Boolean(summary.free_base44_subdomain), crawl_policy: summary.crawl_policy || source?.crawl_policy || {}, crawl_policy_source: source?.crawl_policy_source || summary.crawl_policy?.source || "", url_evidence_summary: summary.url_evidence_summary || source?.url_evidence_summary || {}, crawl_warnings: firstArray([summary.crawl_warnings, source?.crawl_warnings]).slice(0, 20) };
}

function slimScanSummary(summary = {}, healthScore = 0, pagesCrawled = 0, fixes = [], source = {}, summaryText = "") {
  return { ...summary, score: Number(summary.score || summary.health_score || healthScore || 0), health_score: Number(summary.health_score || summary.score || healthScore || 0), status_label: summary.status_label || scoreLabel(healthScore), plain_english_summary: normalizeCoverageSummary(summaryText || summary.plain_english_summary || summary.summary || "", pagesCrawled), pages_scanned: Number(summary.pages_scanned || pagesCrawled || 0), pages_failed: Number(summary.pages_failed || source?.technical_audit_summary?.failed_pages || 0), verified_failed_pages: Number(summary.verified_failed_pages || source?.verified_failed_pages || source?.technical_audit_summary?.verified_failed_pages || 0), suspicious_url_artifacts: Number(summary.suspicious_url_artifacts || source?.suspicious_url_artifacts || source?.technical_audit_summary?.suspicious_url_artifacts || 0), crawl_policy_source: summary.crawl_policy_source || source?.crawl_policy_source || source?.crawl_policy?.source || "", high_priority_count: fixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length, technical_issue_count: fixes.length };
}

function slimHealthReport(report = {}, summaryText = "", healthScore = 0) {
  return { health_score: Number(report.health_score || report.score || healthScore || 0), health_grade: report.health_grade || report.grade || scoreLabel(healthScore), overall_explanation: summaryText || report.overall_explanation || report.summary || "", what_is_working: firstArray([report.what_is_working]).slice(0, 5), top_concerns: firstArray([report.top_concerns]).slice(0, 5), quick_wins: firstArray([report.quick_wins]).slice(0, 5), bigger_projects: firstArray([report.bigger_projects]).slice(0, 5), limitations: firstArray([report.limitations]).slice(0, 5), next_best_step: report.next_best_step || "" };
}

function groupAndSortFixes(fixes, options = {}) {
  const normalized = Array.isArray(fixes) ? fixes.map((fix) => applyBusinessPriorityRules(fix, options)) : [];
  const groups = new Map();
  const keep = [];
  for (const fix of normalized) {
    const affectedCount = firstArray([fix.affected_pages]).length;
    const family = fix.page_template_family || classifyTemplateFamily(fix.page_url || fix.affected_pages?.[0] || "");
    const shouldGroup = affectedCount >= 3 || TEMPLATE_RULES.has(fix.rule) || (fix.is_low_value_page && isCosmeticRule(fix));
    if (!shouldGroup) { keep.push(fix); continue; }
    const key = `${fix.rule || fix.category}|${family}|${fix.priority}`;
    const title = getTemplateGroupTitle(fix, family);
    const existing = groups.get(key) || { ...fix, id: stableId(`group_${key}`), fix_id: stableId(`group_${key}`), page_url: "", title, issue_title: title, plain_english_explanation: getTemplateGroupExplanation(fix), plain_english_summary: getTemplateGroupExplanation(fix), why_it_matters: getTemplateGroupWhy(fix), recommendation: getTemplateGroupRecommendation(fix), recommended_value: getTemplateGroupRecommendation(fix), simple_next_step: getTemplateGroupRecommendation(fix), affected_pages: [], source_pages: [], link_text_samples: [], page_count: 0, difficulty: needsDeveloperOwner(fix) ? "developer" : fix.difficulty, status: needsDeveloperOwner(fix) ? "needs_developer" : fix.status, requires_developer: needsDeveloperOwner(fix) || fix.requires_developer, requires_approval: needsDeveloperOwner(fix) ? false : fix.requires_approval, who_can_do_this: needsDeveloperOwner(fix) ? "your_web_person" : fix.who_can_do_this };
    existing.affected_pages = unique([...existing.affected_pages, ...firstArray([fix.affected_pages]), fix.page_url].filter(Boolean).map(String)).slice(0, 150);
    existing.source_pages = unique([...firstArray([existing.source_pages]), ...firstArray([fix.source_pages])]).slice(0, 30);
    existing.link_text_samples = unique([...firstArray([existing.link_text_samples]), ...firstArray([fix.link_text_samples])]).slice(0, 20);
    existing.page_count = existing.affected_pages.length;
    groups.set(key, existing);
  }
  return dedupeFixes([...keep, ...Array.from(groups.values())]).sort((a, b) => businessSortScore(b, options) - businessSortScore(a, options));
}

function applyBusinessPriorityRules(fix = {}, options = {}) {
  const url = fix.page_url || fix.affected_pages?.[0] || "";
  const lowValue = isLowValuePage(url);
  const important = isImportantBusinessPage(url, options);
  const developerOwned = needsDeveloperOwner(fix);
  let priority = normalizePriority(fix.priority);
  if (lowValue && isCosmeticRule(fix) && !important) priority = "low";
  if (important && priority === "low") priority = "medium";
  if (developerOwned && /route|index|canonical|schema|render|javascript|server|429|500|checkout|login|account/i.test(`${fix.rule} ${fix.title}`)) priority = priority === "low" ? "medium" : priority;
  return { ...fix, priority, requires_developer: developerOwned || fix.requires_developer, requires_approval: developerOwned ? false : fix.requires_approval, difficulty: developerOwned ? "developer" : fix.difficulty, status: developerOwned ? "needs_developer" : fix.status, who_can_do_this: developerOwned ? "your_web_person" : fix.who_can_do_this, business_importance: important ? "important" : lowValue ? "low_value_archive" : fix.business_importance || "standard", is_low_value_page: lowValue, is_important_business_page: important };
}

function buildTopActions({ aiData, finalFixes }) {
  const byId = new Map(finalFixes.map((fix) => [fix.fix_id || fix.id, fix]));
  const output = [];
  const seen = new Set();
  const aiActions = firstArray([aiData?.top_recommended_actions, aiData?.recommended_actions]);
  for (const action of aiActions) {
    const matchingFix = byId.get(action?.fix_id || action?.id) || findSimilarFix(action, finalFixes);
    const hydrated = hydrateActionWithFix(action, matchingFix);
    const key = hydrated.fix_id || hydrated.title;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    output.push(hydrated);
    if (output.length >= 5) return output;
  }
  for (const fix of finalFixes) {
    const key = fix.fix_id || fix.id || fix.title;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    output.push(fixToAction(fix));
    if (output.length >= 5) break;
  }
  return output;
}

function hydrateActionWithFix(action = {}, fix = null) {
  const source = fix || action;
  const title = cleanString(action.title || action.issue_title || fix?.title || fix?.issue_title || "Recommended action");
  const steps = firstArray([action.what_to_do_steps, action.what_to_do, action.steps, fix?.what_to_do_steps, fix?.what_to_do]).slice(0, 5).map(String);
  const developerOwned = needsDeveloperOwner({ ...source, title, what_to_do_steps: steps, who_can_do_this: action.who_can_do_this });
  return { fix_id: action.fix_id || action.id || fix?.fix_id || fix?.id || "", title, reason: cleanString(action.reason || action.why_it_matters || action.plain_english_summary || fix?.why_it_matters || fix?.plain_english_explanation || ""), priority: normalizeActionPriority(action.priority || fix?.priority), plain_english_summary: cleanString(action.plain_english_summary || fix?.plain_english_explanation || action.reason || ""), why_it_matters: cleanString(action.why_it_matters || action.reason || fix?.why_it_matters || ""), what_to_do_steps: steps.length > 0 ? steps : firstArray([fix?.what_to_do_steps, fix?.what_to_do]).slice(0, 5).map(String), who_can_do_this: developerOwned ? "Your web person" : normalizeDisplayOwner(action.who_can_do_this || fix?.who_can_do_this || "You"), time_estimate: action.time_estimate || action.estimated_time || fix?.time_estimate || fix?.estimated_time || "", affected_pages: firstArray([action.affected_pages, fix?.affected_pages]).slice(0, 30) };
}

function findSimilarFix(action = {}, fixes = []) {
  const title = String(action.title || action.issue_title || "").toLowerCase();
  const affected = firstArray([action.affected_pages]).map(String);
  return fixes.find((fix) => affected.some((page) => firstArray([fix.affected_pages]).includes(page))) || fixes.find((fix) => title && String(fix.title || fix.issue_title || "").toLowerCase().includes(title.slice(0, 24)));
}

function fixToAction(fix = {}) {
  return hydrateActionWithFix({ fix_id: fix.fix_id || fix.id, title: fix.title || fix.issue_title, reason: fix.why_it_matters || fix.plain_english_explanation, priority: normalizePriority(fix.priority), affected_pages: fix.affected_pages || [] }, fix);
}

function dedupeFixes(fixes) {
  const seen = new Set();
  const output = [];
  for (const fix of fixes || []) {
    const key = fix.fix_id || fix.id || `${fix.rule}|${fix.title}|${fix.page_url}|${firstArray([fix.affected_pages]).join(",")}`;
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(fix);
  }
  return output;
}

function normalizeCoverageSummary(summary, pagesCrawled) {
  const text = String(summary || "");
  const count = Number(pagesCrawled || 0);
  if (!count || !text) return text;
  return text.replace(/The scanner reviewed\s+\d+\s+pages/gi, `The scanner reviewed ${count} pages`).replace(/scanner reviewed\s+\d+\s+pages/gi, `scanner reviewed ${count} pages`);
}

function normalizeSiteFingerprint(fingerprint = {}, pages = []) {
  const pathText = pages.map((page) => `${page.url || ""} ${page.final_url || ""} ${page.estimated_page_intent || ""}`).join(" ").toLowerCase();
  const bookingHits = countIncludes(pathText, "booking") + countIncludes(pathText, "reservation") + countIncludes(pathText, "ticket") + countIncludes(pathText, "checkout") + countIncludes(pathText, "voucher");
  const energyHits = countIncludes(pathText, "energie") + countIncludes(pathText, "énergie") + countIncludes(pathText, "electricite") + countIncludes(pathText, "électricité") + countIncludes(pathText, "gaz") + countIncludes(pathText, "fournisseur");
  if (energyHits >= 3 && (!fingerprint.primary_archetype || fingerprint.primary_archetype === "finance_insurance_lead_gen" || fingerprint.vertical === "insurance_finance")) return { ...fingerprint, primary_archetype: "utilities_comparison_lead_gen", vertical: "utilities_comparison_lead_gen", archetype_label: "utilities / energy comparison lead generation", vertical_label: "utilities / energy comparison lead generation", business_model: "quote_or_comparison_lead_gen", vertical_confidence: Math.max(Number(fingerprint.vertical_confidence || 0), 0.85) };
  if (bookingHits >= 5 && (!fingerprint.vertical || fingerprint.vertical === "ecommerce")) return { ...fingerprint, primary_archetype: "booking_experiences_marketplace", vertical: "travel_booking", archetype_label: "booking / experiences marketplace", vertical_label: "booking / experiences marketplace", business_model: "booking_or_reservation", vertical_confidence: Math.max(Number(fingerprint.vertical_confidence || 0), 0.85) };
  return fingerprint;
}

function getTemplateGroupTitle(fix = {}, family = "template") { const value = `${fix.rule || ""} ${fix.category || ""} ${fix.title || ""}`.toLowerCase(); const label = String(family || "template").replace(/_/g, " "); if (value.includes("client") || value.includes("javascript") || value.includes("render")) return `Fix crawlable HTML for ${label} pages`; if (value.includes("route") || value.includes("index")) return `Review route-boundary indexing for ${label} pages`; if (value.includes("schema")) return `Add structured data to ${label} templates`; if (value.includes("h1")) return `Fix missing H1 headings on ${label} templates`; if (value.includes("alt")) return `Batch image descriptions on ${label} pages`; if (value.includes("description")) return `Batch meta descriptions on ${label} pages`; return `Fix repeated ${label} template issue`; }
function getTemplateGroupExplanation(fix = {}) { if (/client|javascript|render/i.test(`${fix.rule} ${fix.title}`)) return "Several similar business-critical pages appear to rely on JavaScript for their main content. Treat this as one template rendering issue, not many separate page edits."; if (/route|index/i.test(`${fix.rule} ${fix.title}`)) return "Several checkout, login, account, cart, dashboard, or app-like routes need one route-boundary review."; return "Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page."; }
function getTemplateGroupWhy(fix = {}) { if (/client|javascript|render/i.test(`${fix.rule} ${fix.title}`)) return "Search engines and AI crawlers may not see the booking, listing, product, supplier, or comparison content if it only appears after JavaScript runs."; if (/route|index/i.test(`${fix.rule} ${fix.title}`)) return "Private or checkout/app routes in search can create duplicate, low-trust, or sensitive public pages and can confuse crawlers about what should rank."; return "Large sites usually have template problems. Grouping keeps the FixList focused on the highest-impact patterns."; }
function getTemplateGroupRecommendation(fix = {}) { if (/client|javascript|render/i.test(`${fix.rule} ${fix.title}`)) return "Ask your web person to check whether the main content is visible in page source. Add server-side rendering, pre-rendering, or crawlable fallback HTML for the affected template."; if (/schema/i.test(`${fix.rule} ${fix.title}`)) return "Ask your web person to add the right structured data once at the shared template level, then test a few affected pages."; if (/route|index/i.test(`${fix.rule} ${fix.title}`)) return "Ask your web person to require login, add noindex, or keep private/checkout/account routes out of public search while leaving true public pages crawlable."; return "Fix one representative page/template first, then roll out the same rule across the affected group."; }

function businessSortScore(fix = {}, options = {}) { let score = Number(fix.overall_priority_score || 0); const priorityBonus = { critical: 1000, high: 800, medium: 500, low: 100 }[normalizePriority(fix.priority)] || 300; score += priorityBonus; if (fix.requires_developer && /client|render|javascript|schema|canonical|server|firewall|blocked|429|route|index|checkout|login|account/i.test(`${fix.rule} ${fix.title}`)) score += 130; if (fix.business_importance === "money_page" || fix.is_important_business_page) score += 120; if (isImportantBusinessPage(fix.page_url || fix.affected_pages?.[0] || "", options)) score += 100; if (fix.is_low_value_page || isLowValuePage(fix.page_url || fix.affected_pages?.[0] || "")) score -= 180; if (fix.url_confidence === "crawler_artifact") score -= 300; if ((fix.affected_pages || []).length > 3) score += Math.min(90, fix.affected_pages.length * 4); return score; }
function needsDeveloperOwner(item = {}) { const value = `${item.rule || ""} ${item.category || ""} ${item.title || ""} ${item.issue_title || ""} ${item.reason || ""} ${item.recommendation || ""} ${item.recommended_value || ""} ${firstArray([item.what_to_do_steps, item.what_to_do]).join(" ")} ${item.who_can_do_this || ""} ${item.primary_defect_class || ""}`.toLowerCase(); if (item.requires_developer || item.difficulty === "developer" || item.status === "needs_developer" || value.includes("your_web_person")) return true; return /developer|web person|server-side|server side|ssr|pre-render|prerender|javascript|rendering|schema|structured data|canonical|redirect|server|firewall|bot protection|cloudflare|429|500|503|robots|noindex|crawlable html|view source|indexability|route-boundary|route boundary|checkout|login|account|dashboard/.test(value); }
function normalizeOwner(value) { const owner = String(value || "").toLowerCase(); if (owner.includes("web") || owner.includes("developer") || owner === "your_web_person") return "your_web_person"; return "you"; }
function normalizeDisplayOwner(value) { return normalizeOwner(value) === "your_web_person" ? "Your web person" : "You"; }
function normalizeActionPriority(value) { const priority = normalizePriority(value); return priority === "critical" ? "high" : priority; }
function isCosmeticRule(fix = {}) { return /meta|title|description|thin_content|duplicate|image_alt|alt text|h1/.test(`${fix.rule || ""} ${fix.category || ""} ${fix.title || ""}`.toLowerCase()); }
function isImageAltTextIssue(fix = {}) { return /image_alt_text|image alt|alt text|missing alt|image description/i.test(`${fix.rule || ""} ${fix.category || ""} ${fix.title || ""} ${fix.issue_title || ""}`); }
function isLowValuePage(url = "") { const path = String(url || "").toLowerCase(); if (/\/(20\d{2})([-/]\d{1,2}|\/|$)/.test(path)) return true; return LOW_VALUE_PAGE_PATTERNS.some((pattern) => path.includes(pattern)); }
function isImportantBusinessPage(url = "", options = {}) { const path = String(url || "").toLowerCase(); if (!path) return false; const requested = String(options.requestedPathPrefix || "").toLowerCase(); if (requested && (path === requested || path === `${requested}/` || path.endsWith(`${requested}/index.html`))) return true; return MONEY_PAGE_PATTERNS.some((pattern) => path.includes(pattern)); }
function classifyTemplateFamily(url = "") { const path = String(url || "").toLowerCase(); if (isLowValuePage(path)) return "archive"; if (/checkout|booking|reservation|ticket_order|gift_voucher/.test(path)) return "booking_or_checkout"; if (/listing|show|category|categorie|collection|pass|ticket|stage|pilotage/.test(path)) return "category_listing"; if (/product|produit|\/p\//.test(path)) return "product_detail"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog/.test(path)) return "guide"; if (/privacy|terms|legal|mentions-legales|security|cgv/.test(path)) return "legal_info"; if (/login|register|account|dashboard|admin|billing|cart|checkout/.test(path)) return "route_boundary"; return "standard"; }
function inferCategory(rule = "", fix = {}) { const text = `${rule} ${fix.title || ""} ${fix.issue_title || ""}`.toLowerCase(); if (text.includes("schema") || text.includes("trust")) return "schema"; if (text.includes("canonical")) return "canonical"; if (text.includes("title")) return "meta_title"; if (text.includes("description") || text.includes("meta")) return "meta_description"; if (text.includes("alt")) return "image_alt_text"; if (text.includes("404") || text.includes("broken") || text.includes("blocked")) return "404_error"; if (text.includes("index") || text.includes("noindex")) return "indexability"; if (text.includes("render") || text.includes("javascript")) return "web_dev"; return "web_dev"; }
function defaultTitle(category = "") { const titles = { meta_title: "Improve search titles", meta_description: "Improve search descriptions", duplicate_content: "Review duplicate or repeated pages", canonical: "Review canonical URL setup", schema: "Improve trust and structured data", thin_content: "Improve thin or unclear pages", "404_error": "Fix pages that are not loading", web_dev: "Review website setup", image_alt_text: "Add useful image descriptions", indexability: "Review indexability settings" }; return titles[category] || "Review this recommendation"; }
function friendlyCustomerCategory(category = "") { const map = { meta_title: "Search appearance", meta_description: "Search appearance", duplicate_content: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", mobile_setup: "Mobile setup", performance_hint: "Website performance", social_metadata: "Social sharing", indexability: "Indexability", image_alt_text: "Images" }; return map[category] || "Website improvement"; }
function normalizePriority(value) { const priority = String(value || "").toLowerCase(); if (["critical", "high", "medium", "low"].includes(priority)) return priority; return "medium"; }
function normalizeCmsValue(value) { const normalized = String(value || "custom").toLowerCase(); return CMS_OPTIONS.some((item) => item.value === normalized) ? normalized : "custom"; }
function normalizeWebsiteUrl(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { return new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`).href; } catch { return ""; } }
function normalizeWebsiteKey(value) { try { const url = new URL(value); return `${url.hostname}${url.pathname}`.replace(/\/$/, "").toLowerCase(); } catch { return String(value || "").toLowerCase(); } }
function getRequestedPathPrefix(value) { try { const path = new URL(value).pathname || "/"; if (!path || path === "/") return ""; return path.replace(/\/$/, ""); } catch { return ""; } }
function safeHostname(value) { try { return new URL(String(value || "")).hostname.toLowerCase(); } catch { return ""; } }
function splitLines(value) { return String(value || "").split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean).slice(0, 20); }
function firstArray(values) { for (const value of values || []) if (Array.isArray(value) && value.length > 0) return value; return []; }
function getFirstNumber(values) { for (const value of values || []) { const number = Number(value); if (Number.isFinite(number) && number >= 0) return number; } return 0; }
function unique(values) { return Array.from(new Set((values || []).filter((value) => value !== undefined && value !== null && String(value).trim() !== ""))); }
function cleanString(value) { return typeof value === "string" && value.trim() ? value.trim() : ""; }
function clampText(value, max) { const text = String(value || "").trim(); return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trim()}…`; }
function countIncludes(text, keyword) { const haystack = String(text || "").toLowerCase(); const needle = String(keyword || "").toLowerCase(); if (!needle) return 0; return haystack.split(needle).length - 1; }
function scoreLabel(score) { const number = Number(score || 0); if (number >= 90) return "Excellent"; if (number >= 75) return "Good"; if (number >= 55) return "Fair"; return "Needs work"; }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function getRecommendations(source = {}) { return firstArray([source?.recommendations, source?.cleaned_fixes, source?.fixes, source?.findings, source?.raw_fixes, source?.grouped_findings, source?.issues]); }
function getPages(source = {}) { return firstArray([source?.crawled_pages, source?.pages, source?.scanned_pages, source?.crawl_pages]); }
function getHealthScore(source = {}) { return getFirstNumber([source?.health_score, source?.seo_score, source?.scan_summary?.health_score, source?.scan_summary?.score, source?.website_health_report?.health_score, source?.website_health_report?.score]); }
function buildFallbackSummary({ healthScore, pagesCrawled, finalFixes, cmsName }) { const label = scoreLabel(healthScore); const high = finalFixes.filter((fix) => ["critical", "high"].includes(fix.priority)).length; return `Your website health is currently rated as ${label}. FixList scanned ${pagesCrawled || 0} pages and found ${finalFixes.length} grouped recommendation${finalFixes.length === 1 ? "" : "s"}. ${high > 0 ? `${high} item${high === 1 ? "" : "s"} should be reviewed first.` : "Start with the first recommended fix."} CMS selected: ${cmsName}.`; }
