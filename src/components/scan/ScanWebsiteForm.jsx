import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Bug,
  CheckCircle2,
  Copy,
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

export default function ScanWebsiteForm({ project = null, saving = false }) {
  const navigate = useNavigate();

  const [websiteUrl, setWebsiteUrl] = useState(project?.website_url || "");
  const [businessName, setBusinessName] = useState(project?.business_name || "");
  const [cmsPlatform, setCmsPlatform] = useState(normalizeCmsValue(project?.cms_platform || "custom"));
  const [keywordsText, setKeywordsText] = useState(
    Array.isArray(project?.important_keywords) ? project.important_keywords.join("\n") : ""
  );
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
      await navigator.clipboard.writeText(JSON.stringify(debugData, null, 2));
      setDebugCopied(true);
      window.setTimeout(() => setDebugCopied(false), 1500);
    } catch (copyError) {
      console.warn("Could not copy debug data.", copyError);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    const normalizedUrl = normalizeWebsiteUrl(websiteUrl);
    const requestedPathPrefix = getRequestedPathPrefix(normalizedUrl);
    const trimmedBusinessName = businessName.trim();
    const cmsName = selectedCms?.label || "Custom / Not sure";

    if (!normalizedUrl) {
      setError("Enter a valid website URL.");
      return;
    }

    if (!trimmedBusinessName) {
      setError("Enter the business or website name.");
      return;
    }

    let scanData = null;
    let aiData = null;
    let mergedFinal = null;

    setSubmitting(true);
    clearPreviousDashboardScan(normalizedUrl);

    writeScanDebug({
      status: "running",
      stage: "scan_started",
      website_url: normalizedUrl,
      business_name: trimmedBusinessName,
      cms_platform: cmsPlatform,
      cms_name: cmsName,
      scan_mode: scanMode,
      requested_path_prefix: requestedPathPrefix,
    });
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

      writeScanDebug({
        status: "running",
        stage: "scanner_request_started",
        website_url: normalizedUrl,
        business_name: trimmedBusinessName,
        cms_platform: cmsPlatform,
        cms_name: cmsName,
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        payload_summary: {
          max_pages: scanPayload.max_pages,
          max_competitors: 0,
          max_browser_render_attempts: scanPayload.max_browser_render_attempts,
          crawl_timeout_ms: scanPayload.crawl_timeout_ms,
          keyword_count: scanPayload.important_keywords.length,
        },
      });
      refreshDebugData();

      const scannerResponse = await callBase44Function(ADVANCED_SCANNER_FUNCTION, scanPayload);
      scanData = normalizeFunctionResponse(scannerResponse);

      writeScanDebug({
        status: "running",
        stage: "scanner_complete",
        website_url: normalizedUrl,
        business_name: trimmedBusinessName,
        cms_platform: cmsPlatform,
        cms_name: cmsName,
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        scanner: slimScannerData(scanData),
      });
      refreshDebugData();

      if (scanData?.success === false || scanData?.error) {
        throw new Error(scanData.error || "Website scan failed.");
      }

      setActiveStep("Checking SEO issues");

      try {
        const aiPayload = buildAiReviewPayload({
          scanData,
          businessName: trimmedBusinessName,
          websiteUrl: normalizedUrl,
          cmsPlatform,
          cmsName,
          cleanedKeywords,
          scanMode,
        });

        writeScanDebug({
          status: "running",
          stage: "ai_review_request_started",
          website_url: normalizedUrl,
          business_name: trimmedBusinessName,
          cms_platform: cmsPlatform,
          cms_name: cmsName,
          scan_mode: scanMode,
          requested_path_prefix: requestedPathPrefix,
          scanner: slimScannerData(scanData),
          ai_payload_summary: {
            crawled_pages_count: aiPayload.crawled_pages.length,
            raw_fixes_count: aiPayload.raw_fixes.length,
            competitor_results_count: 0,
          },
        });
        refreshDebugData();

        setActiveStep("Writing your FixList");
        const aiResponse = await callBase44Function(AI_REVIEW_FUNCTION, aiPayload);
        aiData = normalizeFunctionResponse(aiResponse);

        writeScanDebug({
          status: "running",
          stage: "ai_review_complete",
          website_url: normalizedUrl,
          business_name: trimmedBusinessName,
          cms_platform: cmsPlatform,
          cms_name: cmsName,
          scan_mode: scanMode,
          requested_path_prefix: requestedPathPrefix,
          scanner: slimScannerData(scanData),
          ai_review: slimAiData(aiData),
        });
        refreshDebugData();

        if (aiData?.success === false && aiData?.error) {
          console.warn("AI review returned an error.", aiData.error);
        }
      } catch (aiError) {
        console.warn("AI review was skipped or failed.", aiError);
        writeScanDebug({
          status: "running",
          stage: "ai_review_failed_but_continuing",
          website_url: normalizedUrl,
          business_name: trimmedBusinessName,
          cms_platform: cmsPlatform,
          cms_name: cmsName,
          scan_mode: scanMode,
          requested_path_prefix: requestedPathPrefix,
          scanner: slimScannerData(scanData),
          ai_review: slimAiData(aiData),
          ai_error: aiError?.message || String(aiError),
        });
        refreshDebugData();
      }

      setActiveStep("Saving your FixList");
      mergedFinal = mergeScanAndAiReview({
        scanData,
        aiData,
        websiteUrl: normalizedUrl,
        businessName: trimmedBusinessName,
        cmsPlatform,
        cmsName,
        scanMode,
        requestedPathPrefix,
      });

      saveScanForDashboard(mergedFinal);

      writeScanDebug({
        status: "saved",
        stage: "dashboard_saved",
        website_url: normalizedUrl,
        business_name: trimmedBusinessName,
        cms_platform: cmsPlatform,
        cms_name: cmsName,
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        scanner: slimScannerData(scanData),
        ai_review: slimAiData(aiData),
        final_record: slimScanRecord(mergedFinal),
      });
      refreshDebugData();

      navigate("/dashboard?scan=complete");
    } catch (err) {
      console.error("Website scan failed.", err);
      writeScanDebug({
        status: "failed",
        stage: "scan_failed",
        website_url: normalizedUrl,
        business_name: trimmedBusinessName,
        cms_platform: cmsPlatform,
        cms_name: cmsName,
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        error: err?.message || String(err),
        scanner: slimScannerData(scanData),
        ai_review: slimAiData(aiData),
        final_record: slimScanRecord(mergedFinal),
      });
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
            <div className="rounded-2xl bg-indigo-50 p-3 text-indigo-600">
              <Search className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">FixList scan</p>
              <h2 className="mt-1 text-2xl font-bold text-slate-950">Create your FixList</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                Enter a website URL and we’ll turn the scan into a plain-English list of what to fix, what matters most, and what may need a developer.
              </p>
              <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600">
                <ShieldCheck className="h-3.5 w-3.5 text-indigo-600" />
                Read-only scan — FixList never logs in or changes your website.
              </div>
            </div>
          </div>

          <Button type="button" variant="outline" onClick={() => { refreshDebugData(); setDebugOpen((value) => !value); }} className="shrink-0">
            <Bug className="mr-2 h-4 w-4" />
            {debugOpen ? "Hide debug" : "Show debug"}
          </Button>
        </div>

        {debugOpen ? (
          <div className="mt-6 rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-bold text-slate-950">Scan debug</h3>
                <p className="mt-1 text-xs text-slate-500">Compact debug summary for testing the final save step.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={refreshDebugData}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button>
                <Button type="button" variant="outline" onClick={copyDebugData}><Copy className="mr-2 h-4 w-4" />{debugCopied ? "Copied" : "Copy JSON"}</Button>
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
            <div>
              <label className="text-sm font-medium text-slate-700">Website URL</label>
              <Input value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} placeholder="https://www.example.com/" disabled={isLoading} className="mt-2" />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Business or website name</label>
              <Input value={businessName} onChange={(event) => setBusinessName(event.target.value)} placeholder="Example Business" disabled={isLoading} className="mt-2" />
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">Scan size</label>
            <div className="mt-2 grid gap-3 md:grid-cols-3">
              {SCAN_MODES.map((mode) => {
                const active = scanMode === mode.value;
                return (
                  <button
                    key={mode.value}
                    type="button"
                    disabled={isLoading}
                    onClick={() => setScanMode(mode.value)}
                    className={`rounded-2xl border p-4 text-left transition ${active ? "border-indigo-500 bg-indigo-50 text-slate-950 ring-2 ring-indigo-100" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}
                  >
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className={`h-4 w-4 ${active ? "text-indigo-600" : "text-slate-300"}`} />
                      <span className="font-semibold">{mode.label}</span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-500">{mode.description}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <button type="button" onClick={() => setOptionalOpen((value) => !value)} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-100">
            {optionalOpen ? "Hide optional settings" : "Optional: personalize your FixList"}
          </button>

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

        {error ? (
          <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <div className="flex items-start gap-2"><AlertCircle className="mt-0.5 h-4 w-4" /><span>{error}</span></div>
          </div>
        ) : null}

        {isLoading ? (
          <div className="mt-6 rounded-2xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-950">
            <div className="flex items-center gap-3"><Loader2 className="h-4 w-4 animate-spin" /><span>{activeStep || "Running scan..."}</span></div>
          </div>
        ) : null}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button type="submit" disabled={isLoading} className="bg-indigo-600 text-white hover:bg-indigo-700">
            {isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Building FixList...</> : <><Search className="mr-2 h-4 w-4" />Create FixList</>}
          </Button>
          <p className="text-xs text-slate-500">Most scans take 1–2 minutes. Start with Quick check, then use Standard or Full site if needed.</p>
        </div>
      </form>
    </div>
  );
}

function buildAiReviewPayload({ scanData, businessName, websiteUrl, cmsPlatform, cmsName, cleanedKeywords, scanMode }) {
  return {
    business_name: businessName,
    website_url: websiteUrl,
    cms_platform: cmsPlatform,
    cms_name: cmsName,
    important_keywords: cleanedKeywords,
    scan_mode: scanMode,
    ai_review_goal: "Simplify the crawler and Screaming Frog Lite results into a clear customer-friendly FixList. Prioritize fixes by business impact, explain what to do first, and tailor implementation steps to the selected CMS.",
    cms_instruction: buildCmsInstruction(cmsPlatform),
    output_requirements: { keep_language_simple: true, avoid_technical_jargon: true, group_similar_issues: true, create_top_priorities: true, create_cms_specific_steps: true, include_developer_flags_only_when_needed: true, include_joomla_when_selected: true, explain_scan_focus: true, mention_followup_scans_only_if_useful: true },
    crawled_pages: firstArray([scanData?.crawled_pages, scanData?.pages, scanData?.scanned_pages, scanData?.crawl_pages]).slice(0, 80),
    raw_fixes: firstArray([scanData?.raw_fixes, scanData?.grouped_findings, scanData?.raw_findings, scanData?.fixes, scanData?.findings, scanData?.recommendations, scanData?.issues]).slice(0, 120),
    competitor_results: [],
    discovered_competitors: [],
    recommended_followup_scans: firstArray([scanData?.recommended_followup_scans]),
    important_page_patterns: firstArray([scanData?.important_page_patterns]),
    deprioritized_page_patterns: firstArray([scanData?.deprioritized_page_patterns]),
    sitemap_priority_summary: scanData?.sitemap_priority_summary || {},
    crawl_scope: scanData?.crawl_scope || {},
    crawl_warnings: firstArray([scanData?.crawl_warnings]),
    technical_audit_summary: scanData?.technical_audit_summary || {},
    scan_summary: scanData?.scan_summary || scanData?.site_summary || {},
  };
}

function getSafeScanBudget(scanMode) {
  if (scanMode === "advanced") return { max_pages: 150, max_competitors: 0, max_browser_render_attempts: 1, crawl_timeout_ms: 90000 };
  if (scanMode === "deep") return { max_pages: 85, max_competitors: 0, max_browser_render_attempts: 1, crawl_timeout_ms: 75000 };
  return { max_pages: 40, max_competitors: 0, max_browser_render_attempts: 1, crawl_timeout_ms: 45000 };
}

function mergeScanAndAiReview({ scanData, aiData, websiteUrl, businessName, cmsPlatform, cmsName, scanMode, requestedPathPrefix }) {
  const scannerFixes = firstArray([scanData?.raw_fixes, scanData?.grouped_findings, scanData?.raw_findings, scanData?.fixes, scanData?.findings, scanData?.recommendations, scanData?.issues]);
  const aiFixes = firstArray([aiData?.cleaned_fixes, aiData?.recommendations, aiData?.fixes, aiData?.findings, aiData?.raw_fixes]);
  const finalFixes = simplifyAndPrioritizeFixes((aiFixes.length > 0 ? aiFixes : scannerFixes).slice(0, 120));
  const pages = firstArray([scanData?.crawled_pages, scanData?.pages, scanData?.scanned_pages, scanData?.crawl_pages, aiData?.crawled_pages, aiData?.pages]).slice(0, 120);
  const scannerReadablePages = scanData?.technical_audit_summary?.readable_pages_checked || 0;
  const scannerBlockedPages = scanData?.technical_audit_summary?.scanner_blocked_pages || 0;
  const scannerSaysBlocked = scannerReadablePages === 0 && scannerBlockedPages > 0;
  const healthScore = scannerSaysBlocked ? getFirstNumber([scanData?.health_score, scanData?.seo_score, 35]) : getFirstNumber([aiData?.health_score, aiData?.seo_score, aiData?.website_health_report?.score, aiData?.website_health_report?.health_score, aiData?.scan_summary?.health_score, scanData?.health_score, scanData?.seo_score, scanData?.scan_summary?.health_score]);
  const pagesCrawled = getFirstNumber([scanData?.pages_crawled, scanData?.pages_scanned, scanData?.technical_audit_summary?.pages_checked, pages.length]);
  const pagesFound = getFirstNumber([scanData?.pages_found, scanData?.pages_discovered, scanData?.pages_crawled, pages.length]);
  const topActions = firstArray([aiData?.top_recommended_actions, aiData?.recommended_actions]);
  const simpleSummary = aiData?.customer_summary || aiData?.plain_english_summary || aiData?.summary || aiData?.website_health_report?.overall_explanation || scanData?.scan_summary?.summary || scanData?.site_summary?.summary || buildFallbackSummary({ healthScore, pagesCrawled, finalFixes, cmsName });

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
    customer_summary: simpleSummary,
    simple_summary: simpleSummary,
    cms_action_plan: aiData?.cms_action_plan || aiData?.cms_plan || aiData?.implementation_plan || buildCmsActionPlan(cmsPlatform, cmsName, finalFixes),
    top_recommended_actions: topActions.length > 0 ? topActions.slice(0, 5).map(slimAction) : finalFixes.slice(0, 5).map(fixToAction),
    recommendations: finalFixes.map(slimFix),
    fixes: finalFixes.map(slimFix),
    findings: finalFixes.map(slimFix),
    crawled_pages: pages.map(slimPage),
    pages: pages.map(slimPage),
    scanned_pages: pages.map(slimPage),
    scan_summary: slimScanSummary(aiData?.scan_summary || scanData?.scan_summary || scanData?.site_summary || {}, healthScore, pagesCrawled, finalFixes),
    site_summary: slimScanSummary(scanData?.site_summary || scanData?.scan_summary || {}, healthScore, pagesCrawled, finalFixes),
    technical_audit_summary: slimTechnicalSummary(scanData?.technical_audit_summary || {}),
    website_health_report: slimHealthReport(scannerSaysBlocked ? scanData?.website_health_report || scanData?.scan_summary || {} : aiData?.website_health_report || scanData?.website_health_report || {}),
    positive_findings: firstArray([aiData?.positive_findings, scanData?.positive_findings, scanData?.site_summary?.positives]).slice(0, 8).map(String),
    health_explanation: scannerSaysBlocked ? scanData?.health_explanation || "The scanner could not read the page content, so the score is based on scan coverage rather than full SEO checks." : aiData?.health_explanation || scanData?.health_explanation || "",
    crawl_scope: scanData?.crawl_scope || {},
    sitemap_priority_summary: slimSitemapSummary(scanData?.sitemap_priority_summary || {}),
    important_page_patterns: firstArray([scanData?.important_page_patterns, aiData?.important_page_patterns]).slice(0, 20),
    deprioritized_page_patterns: firstArray([scanData?.deprioritized_page_patterns, aiData?.deprioritized_page_patterns]).slice(0, 20),
    recommended_followup_scans: firstArray([scanData?.recommended_followup_scans, aiData?.recommended_followup_scans]).slice(0, 10),
    competitor_result: {},
    competitor_results: [],
    competitor_opportunities: [],
    crawl_warnings: firstArray([scanData?.crawl_warnings, aiData?.crawl_warnings]).slice(0, 10),
    debug: { scanner_function: ADVANCED_SCANNER_FUNCTION, ai_function: AI_REVIEW_FUNCTION, screaming_frog_lite_enabled: true, scanner_success: scanData?.success !== false, ai_success: aiData?.success === true, ai_provider: aiData?.provider || aiData?.ai_provider || aiData?.debug?.provider || "", cms_platform: cmsPlatform, requested_path_prefix: requestedPathPrefix || "", scanner_version: scanData?.version || "", scanner_pages_crawled: scanData?.pages_crawled || 0, scanner_max_pages_effective: scanData?.max_pages_effective || 0, scanner_readable_pages: scannerReadablePages, scanner_blocked_pages: scannerBlockedPages, scanner_says_blocked: scannerSaysBlocked, final_score_source: scannerSaysBlocked ? "scanner" : "ai_then_scanner", saved_as_slim_record: true },
    raw: { scanner: slimScannerData(scanData), ai_review: slimAiData(aiData) },
  };
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
    console.error("Could not save slim scan for dashboard.", storageError);
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
    window.localStorage.setItem(SCAN_DEBUG_KEY, JSON.stringify({ ...slimDebugData(data), updated_at: new Date().toISOString() }));
    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (storageError) {
    console.warn("Could not write compact scan debug data.", storageError);
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
    wordpress: "Tailor fixes for WordPress. Mention SEO plugins such as Yoast, Rank Math, or All in One SEO when useful. Explain where to edit titles, meta descriptions, headings, internal links, schema, redirects, and image alt text.",
    squarespace: "Tailor fixes for Squarespace. Explain steps using page settings, SEO tab, page titles, descriptions, headings, image settings, redirects, and navigation settings.",
    wix: "Tailor fixes for Wix. Explain steps using Wix SEO settings, page SEO basics, URL slugs, headings, alt text, redirects, and structured data tools.",
    shopify: "Tailor fixes for Shopify. Explain steps for products, collections, pages, theme editor, navigation, image alt text, URL redirects, and SEO fields.",
    webflow: "Tailor fixes for Webflow. Explain steps using page settings, CMS collections, SEO settings, Open Graph settings, redirects, alt text, and publishing.",
    framer: "Tailor fixes for Framer. Explain steps using page settings, metadata, headings, redirects where available, components, images, and publishing.",
    godaddy: "Tailor fixes for GoDaddy Website Builder. Explain simple steps using page settings, SEO tools, headings, images, navigation, and redirects if available.",
    joomla: "Tailor fixes for Joomla. Explain steps using Articles, Menus, Global Configuration, Metadata Options, SEF URLs, redirects, extensions, templates, headings, image alt text, and structured data extensions where useful.",
    custom: "Tailor fixes for a custom or unknown CMS. Explain which changes can be made by a site editor and which likely need a developer.",
  };
  return instructions[cmsPlatform] || instructions.custom;
}

function buildCmsActionPlan(cmsPlatform, cmsName, fixes) {
  const priorityCount = Array.isArray(fixes) ? fixes.length : 0;
  const intro = `This website is marked as ${cmsName}. Start with the highest-impact SEO fixes first, then handle the easier cleanup tasks.`;
  const cmsSteps = {
    wordpress: ["Open the page in WordPress.", "Update the SEO title and meta description in Yoast, Rank Math, or your SEO plugin.", "Improve the H1, headings, body copy, internal links, and image alt text.", "Use a redirect plugin for broken or moved URLs."],
    squarespace: ["Open the page settings in Squarespace.", "Update the SEO title, description, URL slug, headings, and image descriptions.", "Use redirects for old or broken URLs.", "Republish and recheck the page."],
    wix: ["Open the page in Wix.", "Use SEO Basics to update the title, description, URL slug, and index settings.", "Improve headings, body content, internal links, and image alt text.", "Use Wix redirects for broken URLs."],
    shopify: ["Open the product, collection, blog post, or page in Shopify.", "Edit the search engine listing preview.", "Improve product or page copy, headings, internal links, and image alt text.", "Use URL redirects for changed or broken pages."],
    webflow: ["Open the page or CMS item in Webflow.", "Update SEO settings, Open Graph fields, headings, and content.", "Fix alt text and internal links.", "Publish the site and recheck the page."],
    framer: ["Open the page settings in Framer.", "Update metadata, headings, page copy, images, and links.", "Republish and recheck the page.", "Use developer help for custom redirects or technical issues."],
    godaddy: ["Open the page in GoDaddy Website Builder.", "Use the SEO/settings area to update page title and description.", "Improve headings, text, navigation, and images.", "Use developer help if redirects or advanced schema are not available."],
    joomla: ["Open the article or menu item in Joomla.", "Update the browser page title, meta description, alias, headings, and article content.", "Check Global Configuration for SEF URLs and site metadata.", "Use Joomla redirects or an SEO extension for broken URLs, canonical issues, and schema."],
    custom: ["Update simple content issues in the CMS editor.", "Send technical items such as redirects, schema, canonicals, and performance to a developer.", "Recheck the page after changes are published."],
  };
  const steps = cmsSteps[cmsPlatform] || cmsSteps.custom;
  return `${intro} There are ${priorityCount} recommendations ready for review.\n\n${steps.map((step, index) => `${index + 1}. ${step}`).join("\n")}`;
}

function simplifyAndPrioritizeFixes(fixes) {
  if (!Array.isArray(fixes)) return [];
  return fixes.map((fix) => slimFix({ ...fix, priority: normalizePriority(fix?.priority), customer_category: fix?.customer_category || friendlyCustomerCategory(fix?.category) || "Website improvement", simple_next_step: fix?.simple_next_step || fix?.next_step || fix?.ai_recommendation || fix?.recommended_value || fix?.recommendation || fix?.suggested_fix || "Review this item and update the affected page." })).sort((a, b) => priorityWeight(b.priority) - priorityWeight(a.priority));
}

async function callBase44Function(functionName, payload) {
  const timeoutMs = functionName === ADVANCED_SCANNER_FUNCTION ? Number(payload?.crawl_timeout_ms || 30000) + 15000 : 70000;
  const callPromise = callBase44FunctionWithoutTimeout(functionName, payload);
  return await Promise.race([callPromise, new Promise((_, reject) => { window.setTimeout(() => reject(new Error(`${functionName} did not return within ${Math.round(timeoutMs / 1000)} seconds. The scan may have timed out before saving results.`)), timeoutMs); })]);
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

function slimDebugData(data = {}) { return { ...data, scanner: data.scanner ? slimScannerData(data.scanner) : data.scanner, ai_review: data.ai_review ? slimAiData(data.ai_review) : data.ai_review, final_record: data.final_record ? slimScanRecord(data.final_record) : data.final_record }; }
function slimScannerData(scanner = {}) { if (!scanner) return null; return { success: scanner.success, version: scanner.version, website_url: scanner.website_url, scan_mode: scanner.scan_mode, max_pages_requested: scanner.max_pages_requested, max_pages_effective: scanner.max_pages_effective, pages_found: scanner.pages_found, pages_crawled: scanner.pages_crawled, queued_remaining: scanner.queued_remaining, health_score: scanner.health_score, seo_score: scanner.seo_score, technical_audit_summary: slimTechnicalSummary(scanner.technical_audit_summary || {}), screaming_frog_lite: scanner.screaming_frog_lite || null, browser_rendering: scanner.browser_rendering || null, crawl_scope: scanner.crawl_scope || {}, crawl_warnings: firstArray([scanner.crawl_warnings]).slice(0, 10), recommendations_count: getRecommendations(scanner).length, pages_preview: getPages(scanner).slice(0, 10).map(slimPage), recommendations_preview: getRecommendations(scanner).slice(0, 12).map(slimFix), debug: { ssrf_hardened: scanner.debug?.ssrf_hardened, skipped_urls: scanner.debug?.skipped_urls, sitemap_entries_found: scanner.debug?.sitemap_entries_found } }; }
function slimAiData(ai = {}) { if (!ai) return null; const recommendations = getRecommendations(ai); return { success: ai.success, ai_provider: ai.ai_provider || ai.provider || ai.debug?.provider || "", ai_review_warning: ai.ai_review_warning || "", health_score: ai.health_score || ai.seo_score || ai.website_health_report?.health_score || ai.website_health_report?.score || 0, customer_summary: ai.customer_summary || ai.plain_english_summary || ai.summary || ai.website_health_report?.overall_explanation || "", website_health_report: slimHealthReport(ai.website_health_report || {}), top_recommended_actions: firstArray([ai.top_recommended_actions, ai.recommended_actions]).slice(0, 5).map(slimAction), recommendations_count: recommendations.length, recommendations_preview: recommendations.slice(0, 12).map(slimFix), ai_rewrites_applied: ai.ai_rewrites_applied || 0 }; }
function slimScanRecord(record = {}) { if (!record) return null; return { id: record.id || `scan_${Date.now()}`, created_at: record.created_at || new Date().toISOString(), website_url: record.website_url || "", website_key: record.website_key || normalizeWebsiteKey(record.website_url || ""), requested_path_prefix: record.requested_path_prefix || "", business_name: record.business_name || "", cms_platform: record.cms_platform || "custom", cms_name: record.cms_name || "Custom / Not sure", scan_mode: record.scan_mode || "quick", health_score: Number(record.health_score || record.seo_score || 0), seo_score: Number(record.seo_score || record.health_score || 0), pages_crawled: Number(record.pages_crawled || getPages(record).length || 0), pages_found: Number(record.pages_found || getPages(record).length || 0), customer_summary: record.customer_summary || record.simple_summary || "", simple_summary: record.simple_summary || record.customer_summary || "", cms_action_plan: record.cms_action_plan || "", top_recommended_actions: firstArray([record.top_recommended_actions]).slice(0, 5).map(slimAction), recommendations: getRecommendations(record).slice(0, 120).map(slimFix), fixes: getRecommendations(record).slice(0, 120).map(slimFix), findings: getRecommendations(record).slice(0, 120).map(slimFix), crawled_pages: getPages(record).slice(0, 120).map(slimPage), pages: getPages(record).slice(0, 120).map(slimPage), scanned_pages: getPages(record).slice(0, 120).map(slimPage), scan_summary: slimScanSummary(record.scan_summary || {}, record.health_score, record.pages_crawled, getRecommendations(record)), site_summary: slimScanSummary(record.site_summary || record.scan_summary || {}, record.health_score, record.pages_crawled, getRecommendations(record)), technical_audit_summary: slimTechnicalSummary(record.technical_audit_summary || {}), website_health_report: slimHealthReport(record.website_health_report || {}), positive_findings: firstArray([record.positive_findings]).slice(0, 8).map(String), health_explanation: record.health_explanation || "", crawl_scope: record.crawl_scope || {}, sitemap_priority_summary: slimSitemapSummary(record.sitemap_priority_summary || {}), important_page_patterns: firstArray([record.important_page_patterns]).slice(0, 20), deprioritized_page_patterns: firstArray([record.deprioritized_page_patterns]).slice(0, 20), recommended_followup_scans: firstArray([record.recommended_followup_scans]).slice(0, 10), competitor_result: {}, competitor_results: [], competitor_opportunities: [], crawl_warnings: firstArray([record.crawl_warnings]).slice(0, 10), debug: record.debug || {}, raw: record.raw || {} }; }
function slimFix(fix = {}) { const affectedPages = firstArray([fix.affected_pages, fix.pages, fix.page_urls]); const fallbackPage = fix.page_url || fix.url || ""; return { id: fix.id || fix.fix_id || fix.fingerprint || stableId(`${fallbackPage}|${fix.category}|${fix.title || fix.issue_title}`), fix_id: fix.fix_id || fix.id || fix.fingerprint || stableId(`${fallbackPage}|${fix.category}|${fix.title || fix.issue_title}`), rule: fix.rule || "", category: fix.category || "web_dev", customer_category: fix.customer_category || friendlyCustomerCategory(fix.category), priority: normalizePriority(fix.priority), difficulty: fix.difficulty || (fix.requires_developer ? "developer" : "easy"), status: fix.status || (fix.requires_developer ? "needs_developer" : fix.can_auto_fix ? "auto_fixed" : "needs_approval"), issue_title: cleanString(fix.issue_title || fix.title || "Review this recommendation"), title: cleanString(fix.title || fix.issue_title || "Review this recommendation"), plain_english_explanation: cleanString(fix.plain_english_explanation || fix.explanation || fix.summary || fix.description || "This recommendation was found during the website scan."), plain_english_summary: cleanString(fix.plain_english_summary || fix.plain_english_explanation || fix.explanation || ""), why_it_matters: cleanString(fix.why_it_matters || fix.why || fix.impact || "Improving this can help visitors and search engines understand the website more clearly."), recommendation: cleanString(fix.recommendation || fix.ai_recommendation || fix.recommended_value || fix.suggested_fix || "Review this recommendation."), recommended_value: cleanString(fix.recommended_value || fix.recommendation || fix.ai_recommendation || fix.suggested_fix || "Review this recommendation."), simple_next_step: cleanString(fix.simple_next_step || fix.next_step || fix.recommended_value || fix.recommendation || "Review this item and update the affected page."), page_url: fallbackPage, affected_pages: unique([...(affectedPages || []), ...(fallbackPage ? [fallbackPage] : [])].map(String)).slice(0, 25), current_value: clampText(fix.current_value || fix.current || "", 240), can_auto_fix: Boolean(fix.can_auto_fix), requires_approval: fix.requires_approval !== false, requires_developer: Boolean(fix.requires_developer), what_to_do: firstArray([fix.what_to_do, fix.what_to_do_steps, fix.fix_steps, fix.steps]).slice(0, 5).map(String), what_to_do_steps: firstArray([fix.what_to_do_steps, fix.what_to_do, fix.fix_steps, fix.steps]).slice(0, 5).map(String), estimated_time: fix.estimated_time || fix.time_estimate || "", confidence_score: typeof fix.confidence_score === "number" ? fix.confidence_score : 90, source: fix.source || "" }; }
function slimPage(page = {}) { return { url: page.url || page.final_url || "", final_url: page.final_url || page.url || "", source: page.source || "", status_code: Number(page.status_code || 0), title: clampText(page.title || "", 140), meta_description: clampText(page.meta_description || "", 220), h1: clampText(page.h1 || "", 140), h1_count: Number(page.h1_count || 0), canonical_url: page.canonical_url || "", robots_meta: page.robots_meta || "", word_count: Number(page.word_count || 0), html_size: Number(page.html_size || 0), image_count: Number(page.image_count || 0), missing_alt_image_count: Number(page.missing_alt_image_count || 0), schema_count: Number(page.schema_count || 0), internal_link_count: Number(page.internal_link_count || 0), indexable: page.indexable !== false, in_sitemap: Boolean(page.in_sitemap), is_scanner_blocked: Boolean(page.is_scanner_blocked), client_rendering_suspected: Boolean(page.client_rendering_suspected) }; }
function slimAction(action = {}) { return { fix_id: action.fix_id || action.id || "", title: cleanString(action.title || action.issue_title || "Recommended action"), reason: cleanString(action.reason || action.why_it_matters || action.plain_english_summary || ""), priority: ["high", "medium", "low"].includes(action.priority) ? action.priority : normalizePriority(action.priority), plain_english_summary: cleanString(action.plain_english_summary || action.reason || ""), why_it_matters: cleanString(action.why_it_matters || action.reason || ""), what_to_do_steps: firstArray([action.what_to_do_steps, action.what_to_do, action.steps]).slice(0, 5).map(String), who_can_do_this: action.who_can_do_this || "You", time_estimate: action.time_estimate || action.estimated_time || "", affected_pages: firstArray([action.affected_pages]).slice(0, 10) }; }
function fixToAction(fix = {}) { return slimAction({ fix_id: fix.fix_id || fix.id, title: fix.title || fix.issue_title, reason: fix.why_it_matters || fix.plain_english_explanation, priority: normalizePriority(fix.priority), affected_pages: fix.affected_pages || [] }); }
function slimTechnicalSummary(summary = {}) { return { audit_profile: summary.audit_profile || "", screaming_frog_lite_enabled: Boolean(summary.screaming_frog_lite_enabled), pages_checked: Number(summary.pages_checked || 0), readable_pages_checked: Number(summary.readable_pages_checked || 0), scanner_blocked_pages: Number(summary.scanner_blocked_pages || 0), important_pages_checked: Number(summary.important_pages_checked || 0), indexable_pages: Number(summary.indexable_pages || 0), missing_meta_description_count: Number(summary.missing_meta_description_count || 0), heavy_page_count: Number(summary.heavy_page_count || 0), average_word_count: Number(summary.average_word_count || 0), checks_completed: firstArray([summary.checks_completed]).slice(0, 30) }; }
function slimScanSummary(summary = {}, healthScore = 0, pagesCrawled = 0, fixes = []) { return { website_url: summary.website_url || "", business_name: summary.business_name || "", health_score: Number(summary.health_score || summary.score || healthScore || 0), score: Number(summary.score || summary.health_score || healthScore || 0), pages_checked: Number(summary.pages_checked || summary.pages_scanned || pagesCrawled || 0), pages_scanned: Number(summary.pages_scanned || summary.pages_checked || pagesCrawled || 0), readable_pages_checked: Number(summary.readable_pages_checked || 0), scanner_blocked_pages: Number(summary.scanner_blocked_pages || 0), total_findings: Number(summary.total_findings || (Array.isArray(fixes) ? fixes.length : 0)), high_priority_findings: Number(summary.high_priority_findings || 0), high_priority_count: Number(summary.high_priority_count || 0), summary: summary.summary || summary.plain_english_summary || "", plain_english_summary: summary.plain_english_summary || summary.summary || "", scan_focus: summary.scan_focus || {}, website_health_report: summary.website_health_report ? slimHealthReport(summary.website_health_report) : undefined }; }
function slimHealthReport(report = {}) { return { health_score: Number(report.health_score || report.score || 0), health_grade: report.health_grade || report.status_label || "", overall_explanation: report.overall_explanation || report.plain_english_summary || report.summary || "", what_is_working: firstArray([report.what_is_working]).slice(0, 5).map(String), top_concerns: firstArray([report.top_concerns]).slice(0, 5), quick_wins: firstArray([report.quick_wins]).slice(0, 5), bigger_projects: firstArray([report.bigger_projects]).slice(0, 5), limitations: firstArray([report.limitations]).slice(0, 5).map(String), next_best_step: report.next_best_step || "" }; }
function slimSitemapSummary(summary = {}) { return { strategy: summary.strategy || "", max_pages_enforced: summary.max_pages_enforced || 0, skipped_urls: summary.skipped_urls || {} }; }
function normalizePriority(priority) { const value = String(priority || "").toLowerCase(); if (["critical", "high", "medium", "low"].includes(value)) return value; return "medium"; }
function priorityWeight(priority) { return { critical: 4, high: 3, medium: 2, low: 1 }[priority] || 2; }
function friendlyCustomerCategory(category) { const map = { meta_title: "Search appearance", meta_description: "Search appearance", canonical: "Website setup", schema: "Trust signals", thin_content: "Page content", duplicate_content: "Search appearance", "404_error": "Broken page", redirect: "Page redirect", internal_link: "Internal links", performance: "Website performance", web_dev: "Website setup", scanner_blocked: "Scan coverage", js_rendering: "Website setup" }; return map[category] || "Website improvement"; }
function buildFallbackSummary({ healthScore, pagesCrawled, finalFixes, cmsName }) { const count = Array.isArray(finalFixes) ? finalFixes.length : 0; return `The scan reviewed ${pagesCrawled || 0} pages and found ${count} recommended improvements. The current health score is ${healthScore || "not available"}. The next steps are tailored for ${cmsName}.`; }
function normalizeWebsiteUrl(value) { const raw = String(value || "").trim(); if (!raw) return ""; try { const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`; const parsed = new URL(withProtocol); parsed.hash = ""; return parsed.toString(); } catch { return ""; } }
function normalizeWebsiteKey(value) { try { const parsed = new URL(value); return `${parsed.hostname.replace(/^www\./i, "")}${parsed.pathname}`; } catch { return String(value || "").trim().toLowerCase(); } }
function getRequestedPathPrefix(value) { try { const parsed = new URL(value); const parts = parsed.pathname.split("/").filter(Boolean); if (parts.length === 0) return ""; const first = parts[0]; if (/^[a-z]{2}(-[a-z]{2})?$/i.test(first)) return `/${first}`; return `/${first}`; } catch { return ""; } }
function normalizeCmsValue(value) { const normalized = String(value || "").toLowerCase().replace(/\s+/g, "_"); const validValues = CMS_OPTIONS.map((item) => item.value); return validValues.includes(normalized) ? normalized : "custom"; }
function splitLines(value) { return String(value || "").split(/\n|,/).map((item) => item.trim()).filter(Boolean); }
function firstArray(values) { for (const value of values || []) { if (Array.isArray(value)) return value; } return []; }
function getFirstNumber(values) { for (const value of values || []) { const number = Number(value); if (Number.isFinite(number) && number > 0) return Math.round(number); } return 0; }
function getRecommendations(record) { if (!record) return []; return firstArray([record.recommendations, record.fixes, record.findings, record.raw_fixes, record.grouped_findings, record.cleaned_fixes, record.raw?.recommendations, record.raw?.fixes, record.raw?.findings, record.raw?.scanner?.raw_fixes, record.raw?.scanner?.grouped_findings, record.raw?.scanner?.recommendations, record.raw?.ai_review?.cleaned_fixes, record.raw?.ai_review?.recommendations]); }
function getPages(record) { if (!record) return []; return firstArray([record.crawled_pages, record.pages, record.scanned_pages, record.crawl_pages, record.raw?.crawled_pages, record.raw?.pages, record.raw?.scanner?.crawled_pages, record.raw?.scanner?.pages]); }
function getHealthScore(record) { if (!record) return 0; return getFirstNumber([record.health_score, record.seo_score, record.scan_summary?.health_score, record.website_health_report?.score, record.website_health_report?.health_score, record.raw?.health_score, record.raw?.seo_score, record.raw?.scanner?.health_score, record.raw?.scanner?.seo_score, record.raw?.ai_review?.health_score, record.raw?.ai_review?.website_health_report?.score, record.raw?.ai_review?.website_health_report?.health_score]); }
function cleanString(value) { if (typeof value === "string" && value.trim()) return value.trim(); return ""; }
function clampText(value, max) { const text = String(value || "").trim(); if (text.length <= max) return text; return text.slice(0, Math.max(0, max - 1)).trim(); }
function stableId(input) { let hash = 0; const value = String(input || ""); for (let i = 0; i < value.length; i += 1) { hash = (hash << 5) - hash + value.charCodeAt(i); hash |= 0; } return `finding_${Math.abs(hash)}`; }
function unique(values) { return Array.from(new Set(values.filter(Boolean))); }
