import React, { useMemo, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Search,
  Sparkles,
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

const SCAN_MODES = [
  {
    value: "quick",
    label: "Quick",
    description: "Good first pass for smaller sites.",
  },
  {
    value: "deep",
    label: "Deep",
    description: "Best default scan for most websites.",
  },
  {
    value: "advanced",
    label: "Advanced",
    description: "Largest scan with deeper page discovery.",
  },
];

export default function ScanWebsiteForm({
  project = null,
  competitors = [],
  saving = false,
  onScan = null,
}) {
  const [websiteUrl, setWebsiteUrl] = useState(project?.website_url || "");
  const [businessName, setBusinessName] = useState(
    project?.business_name || ""
  );
  const [keywordsText, setKeywordsText] = useState(
    Array.isArray(project?.important_keywords)
      ? project.important_keywords.join("\n")
      : ""
  );
  const [competitorUrlsText, setCompetitorUrlsText] = useState(
    getInitialCompetitorUrls(project, competitors).join("\n")
  );
  const [scanMode, setScanMode] = useState(project?.scan_mode || "deep");

  const [submitting, setSubmitting] = useState(false);
  const [activeStep, setActiveStep] = useState("");
  const [error, setError] = useState("");
  const [finalResult, setFinalResult] = useState(null);
  const [debugPayload, setDebugPayload] = useState(null);

  const isLoading = submitting || saving;

  const cleanedKeywords = useMemo(() => {
    return splitLines(keywordsText);
  }, [keywordsText]);

  const cleanedCompetitorUrls = useMemo(() => {
    return splitLines(competitorUrlsText);
  }, [competitorUrlsText]);

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setFinalResult(null);
    setDebugPayload(null);

    const normalizedUrl = normalizeWebsiteUrl(websiteUrl);

    if (!normalizedUrl) {
      setError("Enter a valid website URL.");
      return;
    }

    if (!businessName.trim()) {
      setError("Enter the business or website name.");
      return;
    }

    setSubmitting(true);

    try {
      const formPayload = {
        website_url: normalizedUrl,
        business_name: businessName.trim(),
        important_keywords: cleanedKeywords,
        competitor_urls: cleanedCompetitorUrls,
        scan_mode: scanMode,
      };

      if (typeof onScan === "function") {
        await onScan(formPayload);
        return;
      }

      setActiveStep("Scanning website");

      const scanPayload = {
        website_url: normalizedUrl,
        business_name: businessName.trim(),
        important_keywords: cleanedKeywords,
        competitor_urls: cleanedCompetitorUrls,
        scan_mode: scanMode,

        enable_screaming_frog_lite: true,
        force_internal_crawl: true,
        respect_robots_txt: false,

        source: "scan_website_page",
        requested_at: new Date().toISOString(),
      };

      const scannerResponse = await callBase44Function(
        ADVANCED_SCANNER_FUNCTION,
        scanPayload
      );

      const scanData = normalizeFunctionResponse(scannerResponse);

      if (scanData?.success === false || scanData?.error) {
        throw new Error(scanData.error || "Website scan failed.");
      }

      setActiveStep("Reviewing recommendations with Gemini");

      let aiData = null;

      try {
        const aiPayload = {
          business_name: businessName.trim(),
          website_url: normalizedUrl,
          important_keywords: cleanedKeywords,
          scan_mode: scanMode,

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

          crawl_warnings: firstArray([scanData.crawl_warnings]),
          technical_audit_summary: scanData.technical_audit_summary || {},
          scan_summary: scanData.scan_summary || scanData.site_summary || {},
        };

        const aiResponse = await callBase44Function(
          AI_REVIEW_FUNCTION,
          aiPayload
        );

        aiData = normalizeFunctionResponse(aiResponse);

        if (aiData?.success === false && aiData?.error) {
          console.warn("AI review returned an error.", aiData.error);
        }
      } catch (aiError) {
        console.warn("AI review was skipped or failed.", aiError);
      }

      setActiveStep("Saving scan to Fix List");

      const mergedFinal = mergeScanAndAiReview({
        scanData,
        aiData,
        websiteUrl: normalizedUrl,
        businessName: businessName.trim(),
        scanMode,
      });

      saveScanForDashboard(mergedFinal);

      setFinalResult(mergedFinal);
      setDebugPayload({
        scanner_function: ADVANCED_SCANNER_FUNCTION,
        ai_function: AI_REVIEW_FUNCTION,
        scan_payload: scanPayload,
        scanner_response: scanData,
        ai_response: aiData,
        saved_record: mergedFinal,
      });
    } catch (err) {
      console.error("Website scan failed.", err);
      setError(
        err?.message ||
          "The website scan failed. Check the backend function logs and try again."
      );
    } finally {
      setActiveStep("");
      setSubmitting(false);
    }
  }

  const resultFixes = getRecommendations(finalResult);
  const resultPages = getPages(finalResult);
  const resultScore = getHealthScore(finalResult);

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleSubmit}
        className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div className="flex items-start gap-3">
          <div className="rounded-2xl bg-blue-50 p-3 text-blue-700">
            <Search className="h-6 w-6" />
          </div>

          <div>
            <h2 className="text-2xl font-bold text-slate-950">
              Scan Website
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Run the advanced scanner, review the results with Gemini, and sync
              the completed scan directly to the Fix List.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-5">
          <div>
            <label className="text-sm font-medium text-slate-700">
              Website URL
            </label>
            <Input
              value={websiteUrl}
              onChange={(event) => setWebsiteUrl(event.target.value)}
              placeholder="https://www.example.com/"
              disabled={isLoading}
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
              disabled={isLoading}
              className="mt-2"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">
              Important keywords
            </label>
            <textarea
              value={keywordsText}
              onChange={(event) => setKeywordsText(event.target.value)}
              placeholder={"seo agency\nlocal plumber\nbest activities in paris"}
              disabled={isLoading}
              rows={4}
              className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-50"
            />
            <p className="mt-1 text-xs text-slate-500">
              One keyword per line. Optional, but helpful.
            </p>
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">
              Competitor URLs
            </label>
            <textarea
              value={competitorUrlsText}
              onChange={(event) => setCompetitorUrlsText(event.target.value)}
              placeholder={"https://www.competitor-one.com/\nhttps://www.competitor-two.com/"}
              disabled={isLoading}
              rows={4}
              className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-50"
            />
            <p className="mt-1 text-xs text-slate-500">
              Optional. One competitor URL per line.
            </p>
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">
              Scan depth
            </label>

            <div className="mt-2 grid gap-3 md:grid-cols-3">
              {SCAN_MODES.map((mode) => {
                const active = scanMode === mode.value;

                return (
                  <button
                    key={mode.value}
                    type="button"
                    disabled={isLoading}
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
                  </button>
                );
              })}
            </div>
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

        {isLoading ? (
          <div className="mt-6 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
            <div className="flex items-center gap-3">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{activeStep || "Running scan..."}</span>
            </div>
          </div>
        ) : null}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button type="submit" disabled={isLoading}>
            {isLoading ? (
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
            Uses <span className="font-mono">{ADVANCED_SCANNER_FUNCTION}</span>{" "}
            and syncs to the Fix List.
          </p>
        </div>
      </form>

      {finalResult ? (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                Scan complete
              </div>

              <h2 className="mt-2 text-2xl font-bold text-slate-950">
                Fix List updated
              </h2>

              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                This scan was saved to local storage and the dashboard was
                notified. Open the Fix List to see the synced recommendations.
              </p>
            </div>

            <Button asChild variant="outline">
              <a href="/dashboard">
                <ExternalLink className="mr-2 h-4 w-4" />
                View Fix List
              </a>
            </Button>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <MetricCard
              icon={<BarChart3 className="h-5 w-5" />}
              label="Website Health"
              value={resultScore ? `${resultScore}/100` : "Ready"}
            />

            <MetricCard
              icon={<Search className="h-5 w-5" />}
              label="Pages scanned"
              value={resultPages.length || finalResult.pages_crawled || 0}
            />

            <MetricCard
              icon={<Sparkles className="h-5 w-5" />}
              label="Recommendations"
              value={resultFixes.length}
            />
          </div>

          {Array.isArray(finalResult.crawl_warnings) &&
          finalResult.crawl_warnings.length > 0 ? (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="font-semibold">Scan notes</div>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {finalResult.crawl_warnings.slice(0, 4).map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {resultFixes.length > 0 ? (
            <div className="mt-6">
              <h3 className="font-semibold text-slate-950">
                Top recommendations
              </h3>

              <div className="mt-3 space-y-3">
                {resultFixes.slice(0, 5).map((fix, index) => (
                  <RecommendationCard key={index} fix={fix} />
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-600">
              No recommendations were returned by this scan.
            </div>
          )}

          {debugPayload ? (
            <details className="mt-6">
              <summary className="cursor-pointer text-sm font-medium text-slate-600">
                Debug scan payload
              </summary>

              <pre className="mt-3 max-h-[420px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">
                {JSON.stringify(debugPayload, null, 2)}
              </pre>
            </details>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function MetricCard({ icon, label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-slate-500">
        {icon}
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="mt-2 text-2xl font-bold text-slate-950">{value}</div>
    </div>
  );
}

function RecommendationCard({ fix }) {
  const title =
    fix.issue_title ||
    fix.title ||
    fix.name ||
    fix.recommendation_title ||
    "Website recommendation";

  const description =
    fix.plain_english_explanation ||
    fix.description ||
    fix.explanation ||
    fix.recommendation ||
    fix.ai_recommendation ||
    fix.suggested_fix ||
    "Review this recommendation in the Fix List.";

  const priority = fix.priority || "medium";

  const pages = getAffectedPages(fix);

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h4 className="font-semibold text-slate-950">{title}</h4>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            {description}
          </p>
        </div>

        <span className="w-fit rounded-full bg-white px-3 py-1 text-xs font-semibold capitalize text-slate-600">
          {priority}
        </span>
      </div>

      {pages.length > 0 ? (
        <div className="mt-3 text-xs text-slate-500">
          Affected: {pages.slice(0, 3).join(", ")}
          {pages.length > 3 ? ` +${pages.length - 3} more` : ""}
        </div>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Merge scanner + AI review                                                   */
/* -------------------------------------------------------------------------- */

function mergeScanAndAiReview({ scanData, aiData, websiteUrl, businessName, scanMode }) {
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

  const crawlWarnings = firstArray([
    scanData?.crawl_warnings,
    aiData?.crawl_warnings,
  ]);

  const competitorResult =
    scanData?.competitor_result ||
    scanData?.competitor_results ||
    scanData?.competitor_analysis ||
    aiData?.competitor_result ||
    aiData?.competitor_results ||
    {};

  return {
    id: `scan_${Date.now()}`,
    created_at: new Date().toISOString(),
    website_url: websiteUrl,
    business_name: businessName,
    scan_mode: scanMode,

    health_score: healthScore || 0,
    seo_score: healthScore || 0,
    pages_crawled: pagesCrawled || pages.length || 0,
    pages_found: pagesFound || pages.length || 0,

    recommendations: finalFixes,
    fixes: finalFixes,
    findings: finalFixes,

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

    top_recommended_actions:
      aiData?.top_recommended_actions ||
      aiData?.recommended_actions ||
      [],

    positive_findings:
      aiData?.positive_findings ||
      scanData?.positive_findings ||
      scanData?.site_summary?.positives ||
      [],

    health_explanation:
      aiData?.health_explanation ||
      scanData?.health_explanation ||
      "",

    customer_summary:
      aiData?.customer_summary ||
      aiData?.plain_english_summary ||
      scanData?.customer_summary ||
      "",

    competitor_result: competitorResult,
    competitor_results: firstArray([
      scanData?.competitor_results,
      aiData?.competitor_results,
    ]),
    competitor_opportunities: firstArray([
      scanData?.competitor_opportunities,
      aiData?.competitor_opportunities,
    ]),

    crawl_warnings: crawlWarnings,

    debug: {
      scanner_function: ADVANCED_SCANNER_FUNCTION,
      ai_function: AI_REVIEW_FUNCTION,
      scanner_success: scanData?.success !== false,
      ai_success: aiData?.success === true,
      ai_provider: aiData?.provider || aiData?.debug?.provider || "",
    },

    raw: {
      scanner: scanData,
      ai_review: aiData,
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Fix List sync                                                               */
/* -------------------------------------------------------------------------- */

function saveScanForDashboard(scanRecord) {
  try {
    const normalizedRecord = normalizeScanRecordForStorage(scanRecord);

    const lastScanKeys = [DASHBOARD_LAST_SCAN_KEY, LEGACY_LAST_SCAN_KEY];
    const historyKeys = [DASHBOARD_HISTORY_KEY, LEGACY_HISTORY_KEY];

    lastScanKeys.forEach((key) => {
      window.localStorage.setItem(key, JSON.stringify(normalizedRecord));
    });

    historyKeys.forEach((key) => {
      const existingRaw = window.localStorage.getItem(key);
      const existing = existingRaw ? JSON.parse(existingRaw) : [];
      const history = Array.isArray(existing) ? existing : [];

      const nextHistory = [
        normalizedRecord,
        ...history.filter((item) => item?.id !== normalizedRecord.id),
      ].slice(0, 20);

      window.localStorage.setItem(key, JSON.stringify(nextHistory));
    });

    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not save scan for dashboard.", error);
  }
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
    business_name: record.business_name || "",
    scan_mode: record.scan_mode || "deep",

    health_score: Number(healthScore || 0),
    seo_score: Number(healthScore || 0),
    pages_crawled: Number(record.pages_crawled || pages.length || 0),
    pages_found: Number(record.pages_found || pages.length || 0),

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

    raw: record.raw || record,
  };
}

/* -------------------------------------------------------------------------- */
/* Base44 function caller                                                      */
/* -------------------------------------------------------------------------- */

async function callBase44Function(functionName, payload) {
  const errors = [];

  if (base44?.functions?.invoke) {
    try {
      return await base44.functions.invoke(functionName, payload);
    } catch (error) {
      errors.push(`functions.invoke: ${error?.message || error}`);
    }
  }

  if (typeof base44?.functions?.[functionName] === "function") {
    try {
      return await base44.functions[functionName](payload);
    } catch (error) {
      errors.push(`functions.${functionName}: ${error?.message || error}`);
    }
  }

  if (base44?.integrations?.Core?.InvokeFunction) {
    try {
      return await base44.integrations.Core.InvokeFunction({
        name: functionName,
        body: payload,
      });
    } catch (error) {
      errors.push(`InvokeFunction: ${error?.message || error}`);
    }
  }

  throw new Error(
    `${functionName} failed. ${
      errors.length
        ? errors.join(" | ")
        : "No supported Base44 function caller was found."
    }`
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
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function normalizeWebsiteUrl(value) {
  const raw = String(value || "").trim();

  if (!raw) return "";

  try {
    const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const parsed = new URL(withProtocol);

    return parsed.toString();
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

function getInitialCompetitorUrls(project, competitors) {
  if (Array.isArray(project?.competitor_urls)) {
    return project.competitor_urls.filter(Boolean);
  }

  if (Array.isArray(competitors)) {
    return competitors
      .map((item) => item.website_url || item.url || item.domain || "")
      .filter(Boolean);
  }

  return [];
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

function getAffectedPages(fix = {}) {
  return firstArray([
    fix.affected_pages,
    fix.pages,
    fix.urls,
    fix.page_urls,
  ]).map((item) => String(item || "")).filter(Boolean);
}