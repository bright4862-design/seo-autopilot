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

const STORAGE_KEYS = [
  DASHBOARD_LAST_SCAN_KEY,
  LEGACY_LAST_SCAN_KEY,
  DASHBOARD_HISTORY_KEY,
  LEGACY_HISTORY_KEY,
  ACTIVE_SCAN_URL_KEY,
  ACTIVE_SCAN_STARTED_AT_KEY,
  SCAN_DEBUG_KEY,
];

const SCAN_MODES = [
  {
    value: "quick",
    label: "Quick",
    description: "Emergency reliable scan. Up to 12 pages.",
  },
  {
    value: "deep",
    label: "Deep",
    description: "Reliable scan. Up to 25 pages.",
  },
  {
    value: "advanced",
    label: "Advanced",
    description: "Largest reliable scan. Up to 40 pages.",
  },
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

export default function Onboarding() {
  const navigate = useNavigate();

  const [websiteUrl, setWebsiteUrl] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [cmsPlatform, setCmsPlatform] = useState("custom");
  const [keywordsText, setKeywordsText] = useState("");
  const [competitorUrlsText, setCompetitorUrlsText] = useState("");
  const [scanMode, setScanMode] = useState("quick");

  const [submitting, setSubmitting] = useState(false);
  const [activeStep, setActiveStep] = useState("");
  const [error, setError] = useState("");

  const [debugOpen, setDebugOpen] = useState(false);
  const [debugData, setDebugData] = useState(() => readScanDebugData());
  const [debugCopied, setDebugCopied] = useState(false);

  const selectedCms = CMS_OPTIONS.find((item) => item.value === cmsPlatform);

  const cleanedKeywords = useMemo(() => splitLines(keywordsText), [keywordsText]);
  const cleanedCompetitorUrls = useMemo(
    () => splitLines(competitorUrlsText),
    [competitorUrlsText]
  );

  const activeBudget = getSafeScanBudget(scanMode);

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

      window.setTimeout(() => {
        setDebugCopied(false);
      }, 1500);
    } catch (copyError) {
      console.warn("Could not copy debug data.", copyError);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");

    const normalizedUrl = normalizeWebsiteUrl(websiteUrl);
    const requestedPathPrefix = getRequestedPathPrefix(normalizedUrl);

    if (!normalizedUrl) {
      setError("Enter a valid website URL.");
      return;
    }

    if (!businessName.trim()) {
      setError("Enter the business or website name.");
      return;
    }

    let scanData = null;
    let aiData = null;

    setSubmitting(true);
    clearPreviousDashboardScan(normalizedUrl);

    writeScanDebug({
      status: "running",
      stage: "scan_started",
      website_url: normalizedUrl,
      business_name: businessName.trim(),
      cms_platform: cmsPlatform,
      cms_name: selectedCms?.label || "Custom / Not sure",
      scan_mode: scanMode,
      requested_path_prefix: requestedPathPrefix,
    });

    refreshDebugData();

    try {
      const safeScanBudget = getSafeScanBudget(scanMode);

      setActiveStep("Running emergency reliable crawler checks");

      const scanPayload = {
        website_url: normalizedUrl,
        requested_start_url: normalizedUrl,
        crawl_path_prefix: requestedPathPrefix,
        strict_path_prefix: true,
        clear_previous_scan: true,

        business_name: businessName.trim(),
        cms_platform: cmsPlatform,
        cms_name: selectedCms?.label || "Custom / Not sure",
        important_keywords: cleanedKeywords,
        competitor_urls: cleanedCompetitorUrls,
        scan_mode: scanMode,

        enable_screaming_frog_lite: true,
        force_internal_crawl: true,
        respect_robots_txt: false,

        skip_sitemap_discovery: true,
        emergency_fast_scan: true,

        max_pages: safeScanBudget.max_pages,
        max_competitors: safeScanBudget.max_competitors,
        max_browser_render_attempts: safeScanBudget.max_browser_render_attempts,
        crawl_timeout_ms: safeScanBudget.crawl_timeout_ms,

        source: "onboarding_scan_page_emergency_fast",
        requested_at: new Date().toISOString(),
      };

      writeScanDebug({
        status: "running",
        stage: "scanner_request_started",
        website_url: normalizedUrl,
        business_name: businessName.trim(),
        cms_platform: cmsPlatform,
        cms_name: selectedCms?.label || "Custom / Not sure",
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        payload: scanPayload,
      });

      refreshDebugData();

      const scannerResponse = await callBase44Function(
        ADVANCED_SCANNER_FUNCTION,
        scanPayload
      );

      scanData = normalizeFunctionResponse(scannerResponse);

      writeScanDebug({
        status: "running",
        stage: "scanner_complete",
        website_url: normalizedUrl,
        business_name: businessName.trim(),
        cms_platform: cmsPlatform,
        cms_name: selectedCms?.label || "Custom / Not sure",
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        scanner: scanData,
      });

      refreshDebugData();

      if (scanData?.success === false || scanData?.error) {
        throw new Error(scanData.error || "Website scan failed.");
      }

      setActiveStep("Asking Gemini to simplify the Fix List");

      try {
        const aiPayload = {
          business_name: businessName.trim(),
          website_url: normalizedUrl,
          cms_platform: cmsPlatform,
          cms_name: selectedCms?.label || "Custom / Not sure",
          important_keywords: cleanedKeywords,
          scan_mode: scanMode,

          ai_review_goal:
            "Simplify the crawler and Screaming Frog Lite results into a clear customer-friendly Fix List. Prioritize fixes by business impact and tailor implementation steps to the selected CMS.",

          cms_instruction: buildCmsInstruction(cmsPlatform),

          output_requirements: {
            keep_language_simple: true,
            avoid_technical_jargon: true,
            group_similar_issues: true,
            create_top_priorities: true,
            create_cms_specific_steps: true,
            include_developer_flags_only_when_needed: true,
            include_joomla_when_selected: true,
            explain_scan_focus: true,
            mention_followup_scans_only_if_useful: true,
          },

          crawled_pages: firstArray([
            scanData.crawled_pages,
            scanData.pages,
            scanData.scanned_pages,
            scanData.crawl_pages,
          ]),

          raw_fixes: firstArray([
            scanData.raw_fixes,
            scanData.grouped_findings,
            scanData.raw_findings,
            scanData.fixes,
            scanData.findings,
            scanData.recommendations,
            scanData.issues,
          ]),

          competitor_results: firstArray([
            scanData.competitor_results,
            scanData.discovered_competitors,
            scanData.competitor_opportunities,
          ]),

          discovered_competitors: firstArray([
            scanData.discovered_competitors,
            scanData.created_competitors,
          ]),

          recommended_followup_scans: firstArray([
            scanData.recommended_followup_scans,
          ]),

          important_page_patterns: firstArray([
            scanData.important_page_patterns,
          ]),

          deprioritized_page_patterns: firstArray([
            scanData.deprioritized_page_patterns,
          ]),

          sitemap_priority_summary: scanData.sitemap_priority_summary || {},
          crawl_scope: scanData.crawl_scope || {},
          crawl_warnings: firstArray([scanData.crawl_warnings]),
          technical_audit_summary: scanData.technical_audit_summary || {},
          scan_summary: scanData.scan_summary || scanData.site_summary || {},
        };

        writeScanDebug({
          status: "running",
          stage: "ai_review_request_started",
          website_url: normalizedUrl,
          business_name: businessName.trim(),
          cms_platform: cmsPlatform,
          cms_name: selectedCms?.label || "Custom / Not sure",
          scan_mode: scanMode,
          requested_path_prefix: requestedPathPrefix,
          scanner: scanData,
          ai_payload_summary: {
            crawled_pages_count: aiPayload.crawled_pages.length,
            raw_fixes_count: aiPayload.raw_fixes.length,
            competitor_results_count: aiPayload.competitor_results.length,
          },
        });

        refreshDebugData();

        const aiResponse = await callBase44Function(AI_REVIEW_FUNCTION, aiPayload);
        aiData = normalizeFunctionResponse(aiResponse);

        writeScanDebug({
          status: "running",
          stage: "ai_review_complete",
          website_url: normalizedUrl,
          business_name: businessName.trim(),
          cms_platform: cmsPlatform,
          cms_name: selectedCms?.label || "Custom / Not sure",
          scan_mode: scanMode,
          requested_path_prefix: requestedPathPrefix,
          scanner: scanData,
          ai_review: aiData,
        });

        refreshDebugData();
      } catch (aiError) {
        console.warn("AI review was skipped or failed.", aiError);

        writeScanDebug({
          status: "running",
          stage: "ai_review_failed_but_continuing",
          website_url: normalizedUrl,
          business_name: businessName.trim(),
          cms_platform: cmsPlatform,
          cms_name: selectedCms?.label || "Custom / Not sure",
          scan_mode: scanMode,
          requested_path_prefix: requestedPathPrefix,
          scanner: scanData,
          ai_review: aiData,
          ai_error: aiError?.message || String(aiError),
        });

        refreshDebugData();
      }

      setActiveStep("Saving dashboard summary");

      const mergedFinal = mergeScanAndAiReview({
        scanData,
        aiData,
        websiteUrl: normalizedUrl,
        businessName: businessName.trim(),
        cmsPlatform,
        cmsName: selectedCms?.label || "Custom / Not sure",
        scanMode,
        requestedPathPrefix,
      });

      saveScanForDashboard(mergedFinal);

      writeScanDebug({
        status: "saved",
        stage: "dashboard_saved",
        website_url: normalizedUrl,
        business_name: businessName.trim(),
        cms_platform: cmsPlatform,
        cms_name: selectedCms?.label || "Custom / Not sure",
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        scanner: scanData,
        ai_review: aiData,
        final_record: mergedFinal,
      });

      refreshDebugData();

      navigate("/dashboard?scan=complete");
    } catch (err) {
      console.error("Website scan failed.", err);

      writeScanDebug({
        status: "failed",
        stage: "scan_failed",
        website_url: normalizedUrl,
        business_name: businessName.trim(),
        cms_platform: cmsPlatform,
        cms_name: selectedCms?.label || "Custom / Not sure",
        scan_mode: scanMode,
        requested_path_prefix: requestedPathPrefix,
        error: err?.message || String(err),
        scanner: scanData,
        ai_review: aiData,
      });

      refreshDebugData();

      setError(
        err?.message ||
          "The website scan failed. Try Quick mode or check the backend function logs."
      );
    } finally {
      setActiveStep("");
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="rounded-2xl bg-blue-50 p-3 text-blue-700">
                <Search className="h-6 w-6" />
              </div>

              <div>
                <p className="text-sm font-semibold text-blue-700">
                  Website scanner
                </p>

                <h1 className="mt-1 text-3xl font-bold text-slate-950">
                  Scan Website
                </h1>

                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  Run a focused emergency scan first. Once this returns
                  reliably, increase scan size again.
                </p>
              </div>
            </div>

            <Button
              type="button"
              variant="outline"
              onClick={() => {
                refreshDebugData();
                setDebugOpen((value) => !value);
              }}
              className="shrink-0"
            >
              <Bug className="mr-2 h-4 w-4" />
              {debugOpen ? "Hide debug" : "Show debug"}
            </Button>
          </div>

          {debugOpen ? (
            <div className="mt-6 rounded-3xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="font-bold text-slate-950">Scan debug</h3>
                  <p className="mt-1 text-xs text-slate-500">
                    This panel shows exactly what this scan page is sending.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={refreshDebugData}
                  >
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Refresh
                  </Button>

                  <Button
                    type="button"
                    variant="outline"
                    onClick={copyDebugData}
                  >
                    <Copy className="mr-2 h-4 w-4" />
                    {debugCopied ? "Copied" : "Copy JSON"}
                  </Button>

                  <Button
                    type="button"
                    variant="outline"
                    onClick={clearDebugScanData}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Clear scans
                  </Button>
                </div>
              </div>

              <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
                <pre className="max-h-[460px] overflow-auto p-4 text-xs leading-5 text-slate-100">
                  {JSON.stringify(debugData, null, 2)}
                </pre>
              </div>
            </div>
          ) : null}
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="grid gap-5">
            <div>
              <label className="text-sm font-medium text-slate-700">
                Website URL
              </label>
              <Input
                value={websiteUrl}
                onChange={(event) => setWebsiteUrl(event.target.value)}
                placeholder="https://www.example.com/"
                disabled={submitting}
                className="mt-2"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Business or website name
              </label>
              <Input
                value={businessName}
                onChange={(event) => setBusinessName(event.target.value)}
                placeholder="Example Business"
                disabled={submitting}
                className="mt-2"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                What CMS does this website use?
              </label>

              <select
                value={cmsPlatform}
                onChange={(event) => setCmsPlatform(event.target.value)}
                disabled={submitting}
                className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-950 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-50"
              >
                {CMS_OPTIONS.map((cms) => (
                  <option key={cms.value} value={cms.value}>
                    {cms.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Important keywords
              </label>
              <textarea
                value={keywordsText}
                onChange={(event) => setKeywordsText(event.target.value)}
                placeholder={"local service\nbest product\nnear me"}
                disabled={submitting}
                rows={4}
                className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-50"
              />
              <p className="mt-1 text-xs text-slate-500">
                Optional. One keyword per line.
              </p>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Competitor URLs
              </label>
              <textarea
                value={competitorUrlsText}
                onChange={(event) => setCompetitorUrlsText(event.target.value)}
                placeholder={
                  "https://www.competitor-one.com/\nhttps://www.competitor-two.com/"
                }
                disabled={submitting}
                rows={4}
                className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-50"
              />
              <p className="mt-1 text-xs text-slate-500">
                Optional. Competitor checks are disabled in emergency mode.
              </p>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Scan depth
              </label>

              <div className="mt-2 grid gap-3 md:grid-cols-3">
                {SCAN_MODES.map((mode) => {
                  const active = scanMode === mode.value;
                  const budget = getSafeScanBudget(mode.value);

                  return (
                    <button
                      key={mode.value}
                      type="button"
                      disabled={submitting}
                      onClick={() => setScanMode(mode.value)}
                      className={`rounded-2xl border p-4 text-left transition ${
                        active
                          ? "border-blue-500 bg-blue-50 text-blue-950"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {active ? (
                          <CheckCircle2 className="h-4 w-4 text-blue-700" />
                        ) : (
                          <div className="h-4 w-4 rounded-full border border-slate-300" />
                        )}

                        <span className="font-semibold">{mode.label}</span>
                      </div>

                      <p className="mt-2 text-xs leading-5 text-slate-500">
                        {mode.description}
                      </p>

                      <p className="mt-2 text-xs font-semibold text-slate-700">
                        Sends: {budget.max_pages} pages,{" "}
                        {budget.max_competitors} competitors,{" "}
                        {budget.max_browser_render_attempts} renders,{" "}
                        {Math.round(budget.crawl_timeout_ms / 1000)}s timeout
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-sm font-bold text-slate-950">
                Current payload budget
              </p>
              <p className="mt-2 text-sm text-slate-600">
                This scan page will send{" "}
                <strong>{activeBudget.max_pages} pages</strong>,{" "}
                <strong>{activeBudget.max_competitors} competitors</strong>,{" "}
                <strong>
                  {activeBudget.max_browser_render_attempts} browser renders
                </strong>
                , and a{" "}
                <strong>
                  {Math.round(activeBudget.crawl_timeout_ms / 1000)} second
                  timeout
                </strong>
                .
              </p>
              <p className="mt-2 text-xs text-slate-500">
                It also sends skip_sitemap_discovery=true and
                emergency_fast_scan=true.
              </p>
            </div>
          </div>

          {error ? (
            <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4" />
                <span>{error}</span>
              </div>
            </div>
          ) : null}

          {submitting ? (
            <div className="mt-6 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
              <div className="flex items-center gap-3">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>{activeStep || "Running scan..."}</span>
              </div>
            </div>
          ) : null}

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Scanning...
                </>
              ) : (
                <>
                  <Search className="mr-2 h-4 w-4" />
                  Run website scan
                </>
              )}
            </Button>

            <p className="text-xs text-slate-500">
              Run Quick first. It should return before increasing scan size.
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Budget                                                                      */
/* -------------------------------------------------------------------------- */

function getSafeScanBudget(scanMode) {
  if (scanMode === "advanced") {
    return {
      max_pages: 40,
      max_competitors: 0,
      max_browser_render_attempts: 0,
      crawl_timeout_ms: 30000,
    };
  }

  if (scanMode === "deep") {
    return {
      max_pages: 25,
      max_competitors: 0,
      max_browser_render_attempts: 0,
      crawl_timeout_ms: 25000,
    };
  }

  return {
    max_pages: 12,
    max_competitors: 0,
    max_browser_render_attempts: 0,
    crawl_timeout_ms: 18000,
  };
}

/* -------------------------------------------------------------------------- */
/* Merge scanner + AI                                                          */
/* -------------------------------------------------------------------------- */

function mergeScanAndAiReview({
  scanData,
  aiData,
  websiteUrl,
  businessName,
  cmsPlatform,
  cmsName,
  scanMode,
  requestedPathPrefix,
}) {
  const aiFixes = firstArray([
    aiData?.cleaned_fixes,
    aiData?.raw_fixes,
    aiData?.fixes,
    aiData?.findings,
    aiData?.recommendations,
  ]);

  const scannerFixes = firstArray([
    scanData?.raw_fixes,
    scanData?.grouped_findings,
    scanData?.raw_findings,
    scanData?.fixes,
    scanData?.findings,
    scanData?.recommendations,
    scanData?.issues,
  ]);

  const finalFixes = aiFixes.length > 0 ? aiFixes : scannerFixes;

  const pages = firstArray([
    scanData?.crawled_pages,
    scanData?.pages,
    scanData?.scanned_pages,
    scanData?.crawl_pages,
    aiData?.crawled_pages,
    aiData?.pages,
  ]);

  const healthScore = getFirstNumber([
    aiData?.health_score,
    aiData?.seo_score,
    aiData?.website_health_report?.score,
    aiData?.scan_summary?.health_score,
    scanData?.health_score,
    scanData?.seo_score,
    scanData?.website_health_report?.score,
    scanData?.scan_summary?.health_score,
  ]);

  const pagesCrawled = getFirstNumber([
    scanData?.pages_crawled,
    scanData?.pages_scanned,
    scanData?.technical_audit_summary?.pages_checked,
    pages.length,
  ]);

  const pagesFound = getFirstNumber([
    scanData?.pages_found,
    scanData?.pages_discovered,
    scanData?.pages_crawled,
    pages.length,
  ]);

  const prioritizedFixes = simplifyAndPrioritizeFixes(finalFixes);

  const topActions = firstArray([
    aiData?.top_recommended_actions,
    aiData?.recommended_actions,
  ]);

  const simpleSummary =
    aiData?.customer_summary ||
    aiData?.plain_english_summary ||
    aiData?.summary ||
    `The scan reviewed ${pagesCrawled || pages.length || 0} pages and found ${
      prioritizedFixes.length
    } recommendations.`;

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
    cms_action_plan:
      aiData?.cms_action_plan ||
      aiData?.cms_plan ||
      aiData?.implementation_plan ||
      buildCmsActionPlan(cmsPlatform, cmsName, prioritizedFixes),

    top_recommended_actions:
      topActions.length > 0 ? topActions : prioritizedFixes.slice(0, 5),

    recommendations: prioritizedFixes,
    fixes: prioritizedFixes,
    findings: prioritizedFixes,

    crawled_pages: pages,
    pages,
    scanned_pages: pages,

    scan_summary:
      aiData?.scan_summary ||
      scanData?.scan_summary ||
      scanData?.site_summary ||
      {},

    site_summary:
      scanData?.site_summary ||
      aiData?.site_summary ||
      scanData?.scan_summary ||
      {},

    technical_audit_summary: scanData?.technical_audit_summary || {},

    website_health_report:
      aiData?.website_health_report ||
      scanData?.website_health_report ||
      {},

    crawl_scope: scanData?.crawl_scope || {},
    sitemap_priority_summary: scanData?.sitemap_priority_summary || {},
    important_page_patterns: firstArray([
      scanData?.important_page_patterns,
      aiData?.important_page_patterns,
    ]),
    deprioritized_page_patterns: firstArray([
      scanData?.deprioritized_page_patterns,
      aiData?.deprioritized_page_patterns,
    ]),
    recommended_followup_scans: firstArray([
      scanData?.recommended_followup_scans,
      aiData?.recommended_followup_scans,
    ]),

    competitor_result:
      scanData?.competitor_result ||
      scanData?.competitor_results ||
      aiData?.competitor_result ||
      aiData?.competitor_results ||
      {},

    competitor_results: firstArray([
      scanData?.competitor_results,
      aiData?.competitor_results,
    ]),

    competitor_opportunities: firstArray([
      scanData?.competitor_opportunities,
      aiData?.competitor_opportunities,
    ]),

    crawl_warnings: firstArray([
      scanData?.crawl_warnings,
      aiData?.crawl_warnings,
    ]),

    debug: {
      scanner_function: ADVANCED_SCANNER_FUNCTION,
      ai_function: AI_REVIEW_FUNCTION,
      scanner_success: scanData?.success !== false,
      ai_success: aiData?.success === true,
      scanner_version: scanData?.version || "",
      scanner_pages_crawled: scanData?.pages_crawled || 0,
      scanner_max_pages_effective: scanData?.max_pages_effective || 0,
      scanner_readable_pages:
        scanData?.technical_audit_summary?.readable_pages_checked || 0,
      scanner_blocked_pages:
        scanData?.technical_audit_summary?.scanner_blocked_pages || 0,
    },

    raw: {
      scanner: scanData,
      ai_review: aiData,
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Storage                                                                     */
/* -------------------------------------------------------------------------- */

function clearPreviousDashboardScan(activeUrl) {
  try {
    [
      DASHBOARD_LAST_SCAN_KEY,
      LEGACY_LAST_SCAN_KEY,
      DASHBOARD_HISTORY_KEY,
      LEGACY_HISTORY_KEY,
      SCAN_DEBUG_KEY,
    ].forEach((key) => {
      window.localStorage.removeItem(key);
    });

    if (activeUrl) {
      window.localStorage.setItem(ACTIVE_SCAN_URL_KEY, activeUrl);
      window.localStorage.setItem(
        ACTIVE_SCAN_STARTED_AT_KEY,
        new Date().toISOString()
      );
    }

    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not clear previous dashboard scan.", error);
  }
}

function clearAllDashboardScanData() {
  try {
    STORAGE_KEYS.forEach((key) => {
      window.localStorage.removeItem(key);
    });

    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not clear scan data.", error);
  }
}

function saveScanForDashboard(scanRecord) {
  try {
    const normalizedRecord = normalizeScanRecordForStorage(scanRecord);

    [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY].forEach((key) => {
      window.localStorage.setItem(key, JSON.stringify(normalizedRecord));
    });

    [DASHBOARD_HISTORY_KEY, LEGACY_HISTORY_KEY].forEach((key) => {
      const existingRaw = window.localStorage.getItem(key);
      const existing = existingRaw ? JSON.parse(existingRaw) : [];
      const history = Array.isArray(existing) ? existing : [];

      const nextHistory = [
        normalizedRecord,
        ...history.filter(
          (item) => item?.website_key !== normalizedRecord.website_key
        ),
      ].slice(0, 20);

      window.localStorage.setItem(key, JSON.stringify(nextHistory));
    });

    window.localStorage.removeItem(ACTIVE_SCAN_URL_KEY);
    window.localStorage.removeItem(ACTIVE_SCAN_STARTED_AT_KEY);

    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not save scan for dashboard.", error);
  }
}

function writeScanDebug(data) {
  try {
    window.localStorage.setItem(
      SCAN_DEBUG_KEY,
      JSON.stringify({
        ...data,
        updated_at: new Date().toISOString(),
      })
    );

    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not write scan debug data.", error);
  }
}

function readScanDebugData() {
  if (typeof window === "undefined") {
    return {
      raw: {},
      parsed: {},
    };
  }

  const raw = {};
  const parsed = {};

  STORAGE_KEYS.forEach((key) => {
    const value = window.localStorage.getItem(key);
    raw[key] = value;

    try {
      parsed[key] = value ? JSON.parse(value) : null;
    } catch {
      parsed[key] = value;
    }
  });

  return {
    read_at: new Date().toISOString(),
    raw,
    parsed,
  };
}

function normalizeScanRecordForStorage(record) {
  const fixes = getRecommendations(record);
  const pages = getPages(record);
  const healthScore = getHealthScore(record);

  return {
    ...record,
    id: record.id || `scan_${Date.now()}`,
    created_at: record.created_at || new Date().toISOString(),

    website_url: record.website_url || "",
    website_key: normalizeWebsiteKey(record.website_url || ""),
    requested_path_prefix: record.requested_path_prefix || "",

    business_name: record.business_name || "",
    cms_platform: record.cms_platform || "custom",
    cms_name: record.cms_name || "Custom / Not sure",
    scan_mode: record.scan_mode || "quick",

    health_score: Number(healthScore || 0),
    seo_score: Number(healthScore || 0),
    pages_crawled: Number(record.pages_crawled || pages.length || 0),
    pages_found: Number(record.pages_found || pages.length || 0),

    customer_summary: record.customer_summary || record.simple_summary || "",
    simple_summary: record.simple_summary || record.customer_summary || "",
    cms_action_plan: record.cms_action_plan || "",

    top_recommended_actions: Array.isArray(record.top_recommended_actions)
      ? record.top_recommended_actions
      : [],

    recommendations: fixes,
    fixes,
    findings: fixes,

    crawled_pages: pages,
    pages,
    scanned_pages: pages,

    scan_summary: record.scan_summary || {},
    site_summary: record.site_summary || {},
    technical_audit_summary: record.technical_audit_summary || {},
    website_health_report: record.website_health_report || {},

    crawl_scope: record.crawl_scope || {},
    sitemap_priority_summary: record.sitemap_priority_summary || {},
    important_page_patterns: Array.isArray(record.important_page_patterns)
      ? record.important_page_patterns
      : [],
    deprioritized_page_patterns: Array.isArray(
      record.deprioritized_page_patterns
    )
      ? record.deprioritized_page_patterns
      : [],
    recommended_followup_scans: Array.isArray(
      record.recommended_followup_scans
    )
      ? record.recommended_followup_scans
      : [],

    competitor_result: record.competitor_result || {},
    competitor_results: Array.isArray(record.competitor_results)
      ? record.competitor_results
      : [],
    competitor_opportunities: Array.isArray(record.competitor_opportunities)
      ? record.competitor_opportunities
      : [],

    crawl_warnings: Array.isArray(record.crawl_warnings)
      ? record.crawl_warnings
      : [],

    debug: record.debug || {},
    raw: record.raw || record,
  };
}

/* -------------------------------------------------------------------------- */
/* Base44 calls                                                                */
/* -------------------------------------------------------------------------- */

async function callBase44Function(functionName, payload) {
  const timeoutMs =
    functionName === ADVANCED_SCANNER_FUNCTION
      ? Number(payload?.crawl_timeout_ms || 18000) + 15000
      : 70000;

  const callPromise = callBase44FunctionWithoutTimeout(functionName, payload);

  return await Promise.race([
    callPromise,
    new Promise((_, reject) => {
      window.setTimeout(() => {
        reject(
          new Error(
            `${functionName} did not return within ${Math.round(
              timeoutMs / 1000
            )} seconds. The scan may have timed out before saving results.`
          )
        );
      }, timeoutMs);
    }),
  ]);
}

async function callBase44FunctionWithoutTimeout(functionName, payload) {
  if (base44?.functions?.invoke) {
    return await base44.functions.invoke(functionName, payload);
  }

  if (typeof base44?.functions?.[functionName] === "function") {
    return await base44.functions[functionName](payload);
  }

  throw new Error(
    `${functionName} failed. No supported Base44 function caller was found.`
  );
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

/* -------------------------------------------------------------------------- */
/* CMS                                                                         */
/* -------------------------------------------------------------------------- */

function buildCmsInstruction(cmsPlatform) {
  const instructions = {
    wordpress:
      "Tailor fixes for WordPress. Mention SEO plugins such as Yoast, Rank Math, or All in One SEO when useful.",
    squarespace:
      "Tailor fixes for Squarespace. Explain steps using page settings, SEO tab, page titles, descriptions, headings, image settings, redirects, and navigation settings.",
    wix:
      "Tailor fixes for Wix. Explain steps using Wix SEO settings, page SEO basics, URL slugs, headings, alt text, redirects, and structured data tools.",
    shopify:
      "Tailor fixes for Shopify. Explain steps for products, collections, pages, theme editor, navigation, image alt text, URL redirects, and SEO fields.",
    webflow:
      "Tailor fixes for Webflow. Explain steps using page settings, CMS collections, SEO settings, Open Graph settings, redirects, alt text, and publishing.",
    framer:
      "Tailor fixes for Framer. Explain steps using page settings, metadata, headings, redirects where available, components, images, and publishing.",
    godaddy:
      "Tailor fixes for GoDaddy Website Builder. Explain simple steps using page settings, SEO tools, headings, images, navigation, and redirects if available.",
    joomla:
      "Tailor fixes for Joomla. Explain steps using Articles, Menus, Global Configuration, Metadata Options, SEF URLs, redirects, extensions, templates, headings, image alt text, and structured data extensions where useful.",
    custom:
      "Tailor fixes for a custom or unknown CMS. Explain which changes can be made by a site editor and which likely need a developer.",
  };

  return instructions[cmsPlatform] || instructions.custom;
}

function buildCmsActionPlan(cmsPlatform, cmsName, fixes) {
  const priorityCount = Array.isArray(fixes) ? fixes.length : 0;

  const intro = `This website is marked as ${cmsName}. Start with the highest-impact SEO fixes first.`;

  const cmsSteps = {
    wordpress: [
      "Open the page in WordPress.",
      "Update the SEO title and meta description in Yoast, Rank Math, or your SEO plugin.",
      "Improve headings, copy, internal links, and image alt text.",
      "Use a redirect plugin for broken or moved URLs.",
    ],
    squarespace: [
      "Open the page settings in Squarespace.",
      "Update the SEO title, description, URL slug, headings, and image descriptions.",
      "Use redirects for old or broken URLs.",
      "Republish and recheck the page.",
    ],
    wix: [
      "Open the page in Wix.",
      "Use SEO Basics to update the title, description, URL slug, and index settings.",
      "Improve headings, content, links, and image alt text.",
      "Use Wix redirects for broken URLs.",
    ],
    shopify: [
      "Open the product, collection, blog post, or page in Shopify.",
      "Edit the search engine listing preview.",
      "Improve page copy, headings, links, and image alt text.",
      "Use URL redirects for changed or broken pages.",
    ],
    webflow: [
      "Open the page or CMS item in Webflow.",
      "Update SEO settings, Open Graph fields, headings, and content.",
      "Fix alt text and internal links.",
      "Publish the site and recheck the page.",
    ],
    framer: [
      "Open the page settings in Framer.",
      "Update metadata, headings, page copy, images, and links.",
      "Republish and recheck the page.",
      "Use developer help for custom redirects or technical issues.",
    ],
    godaddy: [
      "Open the page in GoDaddy Website Builder.",
      "Use the SEO/settings area to update page title and description.",
      "Improve headings, text, navigation, and images.",
      "Use developer help if redirects or advanced schema are not available.",
    ],
    joomla: [
      "Open the article or menu item in Joomla.",
      "Update the browser page title, meta description, alias, headings, and article content.",
      "Check Global Configuration for SEF URLs and site metadata.",
      "Use Joomla redirects or an SEO extension for broken URLs, canonical issues, and schema.",
    ],
    custom: [
      "Update simple content issues in the CMS editor.",
      "Send technical items such as redirects, schema, canonicals, and performance to a developer.",
      "Recheck the page after changes are published.",
    ],
  };

  const steps = cmsSteps[cmsPlatform] || cmsSteps.custom;

  return `${intro} There are ${priorityCount} recommendations ready for review.\n\n${steps
    .map((step, index) => `${index + 1}. ${step}`)
    .join("\n")}`;
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function normalizeWebsiteUrl(value) {
  const raw = String(value || "").trim();

  if (!raw) return "";

  try {
    const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const parsed = new URL(withProtocol);

    parsed.hash = "";

    return parsed.toString();
  } catch {
    return "";
  }
}

function normalizeWebsiteKey(value) {
  try {
    const parsed = new URL(value);

    return `${parsed.hostname.replace(/^www\./i, "")}${parsed.pathname}`;
  } catch {
    return String(value || "").trim().toLowerCase();
  }
}

function getRequestedPathPrefix(value) {
  try {
    const parsed = new URL(value);
    const parts = parsed.pathname.split("/").filter(Boolean);

    if (parts.length === 0) return "";

    const first = parts[0];

    if (/^[a-z]{2}(-[a-z]{2})?$/i.test(first)) {
      return `/${first}`;
    }

    return `/${first}`;
  } catch {
    return "";
  }
}

function splitLines(value) {
  return String(value || "")
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function firstArray(values) {
  for (const value of values) {
    if (Array.isArray(value)) return value;
  }

  return [];
}

function getFirstNumber(values) {
  for (const value of values) {
    const number = Number(value);

    if (Number.isFinite(number) && number > 0) {
      return Math.round(number);
    }
  }

  return 0;
}

function getRecommendations(record) {
  if (!record) return [];

  return firstArray([
    record.recommendations,
    record.fixes,
    record.findings,
    record.raw_fixes,
    record.grouped_findings,
    record.raw?.recommendations,
    record.raw?.fixes,
    record.raw?.findings,
    record.raw?.scanner?.raw_fixes,
    record.raw?.scanner?.grouped_findings,
    record.raw?.scanner?.recommendations,
    record.raw?.ai_review?.cleaned_fixes,
    record.raw?.ai_review?.recommendations,
  ]);
}

function getPages(record) {
  if (!record) return [];

  return firstArray([
    record.crawled_pages,
    record.pages,
    record.scanned_pages,
    record.crawl_pages,
    record.raw?.crawled_pages,
    record.raw?.pages,
    record.raw?.scanner?.crawled_pages,
    record.raw?.scanner?.pages,
  ]);
}

function getHealthScore(record) {
  if (!record) return 0;

  return getFirstNumber([
    record.health_score,
    record.seo_score,
    record.scan_summary?.health_score,
    record.website_health_report?.score,
    record.raw?.health_score,
    record.raw?.seo_score,
    record.raw?.scanner?.health_score,
    record.raw?.scanner?.seo_score,
    record.raw?.ai_review?.health_score,
    record.raw?.ai_review?.website_health_report?.score,
  ]);
}

function simplifyAndPrioritizeFixes(fixes) {
  if (!Array.isArray(fixes)) return [];

  return fixes
    .map((fix) => {
      const priority = normalizePriority(fix.priority);

      return {
        ...fix,
        priority,
        customer_category:
          fix.customer_category ||
          friendlyCustomerCategory(fix.category) ||
          "Website improvement",
        simple_next_step:
          fix.simple_next_step ||
          fix.next_step ||
          fix.ai_recommendation ||
          fix.recommended_value ||
          fix.recommendation ||
          fix.suggested_fix ||
          "Review this item and update the affected page.",
      };
    })
    .sort((a, b) => priorityWeight(b.priority) - priorityWeight(a.priority));
}

function normalizePriority(priority) {
  const value = String(priority || "").toLowerCase();

  if (["critical", "high", "medium", "low"].includes(value)) return value;

  return "medium";
}

function priorityWeight(priority) {
  const map = {
    critical: 4,
    high: 3,
    medium: 2,
    low: 1,
  };

  return map[priority] || 2;
}

function friendlyCustomerCategory(category) {
  const map = {
    meta_title: "Search appearance",
    meta_description: "Search appearance",
    canonical: "Website setup",
    schema: "Trust signals",
    thin_content: "Page content",
    duplicate_content: "Search appearance",
    "404_error": "Broken page",
    redirect: "Page redirect",
    internal_link: "Internal links",
    performance: "Website performance",
    web_dev: "Website setup",
    scanner_blocked: "Scan coverage",
    js_rendering: "Website setup",
  };

  return map[category] || "Website improvement";
}