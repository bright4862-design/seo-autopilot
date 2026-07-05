import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, AlertCircle, CheckCircle2, Bug } from "lucide-react";
import { base44 } from "@/api/base44Client";

const ADVANCED_SCANNER_FUNCTION = "runAdvancedScan";
const AI_REVIEW_FUNCTION = "runAiReview";

const DEFAULT_COMPETITOR_FIELDS = ["", "", ""];

export default function ScanWebsiteForm() {
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("us");
  const [language, setLanguage] = useState("en");
  const [scanMode, setScanMode] = useState("quick");
  const [competitorUrls, setCompetitorUrls] = useState([
    ...DEFAULT_COMPETITOR_FIELDS,
  ]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scanResult, setScanResult] = useState(null);
  const [reviewResult, setReviewResult] = useState(null);
  const [finalResult, setFinalResult] = useState(null);
  const [showDebug, setShowDebug] = useState(false);

  const finalPages = useMemo(() => {
    return pickFirstNonEmptyArray([
      finalResult?.crawled_pages,
      finalResult?.pages,
      scanResult?.crawled_pages,
      scanResult?.pages,
    ]);
  }, [finalResult, scanResult]);

  const finalFixes = useMemo(() => {
    return pickFirstNonEmptyArray([
      finalResult?.cleaned_fixes,
      finalResult?.raw_fixes,
      finalResult?.fixes,
      finalResult?.findings,
      finalResult?.recommendations,
      scanResult?.raw_fixes,
      scanResult?.grouped_findings,
      scanResult?.raw_findings,
    ]).map(normalizeFixForDisplay);
  }, [finalResult, scanResult]);

  const finalSummary =
    finalResult?.scan_summary?.plain_english_summary ||
    finalResult?.plain_english_summary ||
    scanResult?.scan_summary?.plain_english_summary ||
    scanResult?.site_summary?.plain_english_summary ||
    "Run a scan to see recommendations.";

  const visibleWarnings = (scanResult?.crawl_warnings || []).filter(
    (warning) => {
      const text = String(warning || "");

      return (
        !text.includes("Google competitor discovery is not configured") &&
        !text.includes("SerpAPI competitor discovery is not configured")
      );
    }
  );

  async function handleSubmit(event) {
    event.preventDefault();

    setLoading(true);
    setError("");
    setScanResult(null);
    setReviewResult(null);
    setFinalResult(null);
    setShowDebug(false);

    try {
      const cleanedCompetitorUrls = competitorUrls
        .map((url) => String(url || "").trim())
        .filter(Boolean);

      const scannerPayload = {
        website_url: String(websiteUrl || "").trim(),
        business_name: String(businessName || "").trim(),
        business_type: String(businessType || "").trim(),
        city: String(city || "").trim(),
        country: String(country || "us").trim().toLowerCase(),
        language: String(language || "en").trim().toLowerCase(),
        scan_mode: scanMode,
        enable_screaming_frog_lite: true,
        competitor_urls: cleanedCompetitorUrls,
      };

      if (!scannerPayload.website_url) {
        throw new Error("Enter a website URL before scanning.");
      }

      console.log("SCAN WEBSITE PAYLOAD", scannerPayload);

      const rawScannerResponse = await callBase44Function(
        ADVANCED_SCANNER_FUNCTION,
        scannerPayload
      );

      const scanner = normalizeScanResult(
        unwrapFunctionResponse(rawScannerResponse)
      );

      setScanResult(scanner);

      const aiPayload = {
        ...scannerPayload,

        website_url: scanner.normalized_url || scannerPayload.website_url,
        normalized_url: scanner.normalized_url || scannerPayload.website_url,
        scan_mode: scanner.scan_mode || scanMode,

        crawled_pages: scanner.crawled_pages || [],
        pages: scanner.crawled_pages || [],

        raw_fixes: scanner.raw_fixes || [],
        grouped_findings: scanner.grouped_findings || scanner.raw_fixes || [],
        raw_findings: scanner.raw_findings || scanner.raw_fixes || [],
        fixes: scanner.raw_fixes || [],
        findings: scanner.raw_fixes || [],
        recommendations: scanner.raw_fixes || [],

        health_score: scanner.health_score,
        scan_summary: scanner.scan_summary || null,
        site_summary: scanner.site_summary || null,
        crawl_warnings: scanner.crawl_warnings || [],

        client_rendering: scanner.client_rendering || null,
        technical_audit_summary: scanner.technical_audit_summary || null,
        screaming_frog_lite_enabled: scanner.screaming_frog_lite_enabled,
        audit_profile: scanner.audit_profile || "",

        competitor_urls: cleanedCompetitorUrls,
        competitor_results: scanner.competitor_results || [],
        competitor_page_snapshots: scanner.competitor_page_snapshots || [],
        competitor_comparison: scanner.competitor_comparison || null,
      };

      let review = null;

      try {
        const rawReviewResponse = await callBase44Function(
          AI_REVIEW_FUNCTION,
          aiPayload
        );

        review = normalizeReviewResult(
          unwrapFunctionResponse(rawReviewResponse),
          scanner
        );
      } catch (aiError) {
        review = {
          success: true,
          ai_review_warning: aiError?.message || "AI review failed.",
          cleaned_fixes: scanner.raw_fixes || [],
          raw_fixes: scanner.raw_fixes || [],
          fixes: scanner.raw_fixes || [],
          findings: scanner.raw_fixes || [],
          recommendations: scanner.raw_fixes || [],
          recommended_actions: [],
          top_recommended_actions: [],
          competitor_insights: scanner.competitor_insights || [],
          crawled_pages: scanner.crawled_pages || [],
          pages: scanner.crawled_pages || [],
          scan_summary: scanner.scan_summary || null,
        };
      }

      setReviewResult(review);

      const reviewFixes = pickFirstNonEmptyArray([
        review.cleaned_fixes,
        review.raw_fixes,
        review.fixes,
        review.findings,
        review.recommendations,
      ]);

      setFinalResult({
        ...scanner,
        ...review,

        crawled_pages: review.crawled_pages?.length
          ? review.crawled_pages
          : scanner.crawled_pages,

        pages: review.pages?.length ? review.pages : scanner.crawled_pages,

        cleaned_fixes: reviewFixes.length ? reviewFixes : scanner.raw_fixes,
        raw_fixes: reviewFixes.length ? reviewFixes : scanner.raw_fixes,
        fixes: reviewFixes.length ? reviewFixes : scanner.raw_fixes,
        findings: reviewFixes.length ? reviewFixes : scanner.raw_fixes,
        recommendations: reviewFixes.length ? reviewFixes : scanner.raw_fixes,

        competitor_insights: review.competitor_insights?.length
          ? review.competitor_insights
          : scanner.competitor_insights || [],
      });
    } catch (err) {
      console.error("SCAN WEBSITE FAILED", err);
      setError(err?.message || "Scan failed.");
    } finally {
      setLoading(false);
    }
  }

  function updateCompetitorUrl(index, value) {
    setCompetitorUrls((current) => {
      const copy = [...current];
      copy[index] = value;
      return copy;
    });
  }

  return (
    <div className="w-full max-w-5xl mx-auto space-y-6">
      <form
        onSubmit={handleSubmit}
        className="space-y-6 rounded-2xl border bg-white p-6 shadow-sm"
      >
        <div>
          <h2 className="text-2xl font-semibold text-slate-950">
            Scan Website
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Crawl a website, review technical SEO, and optionally compare manual
            competitor URLs.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="website_url">Website URL</Label>
            <Input
              id="website_url"
              value={websiteUrl}
              onChange={(event) => setWebsiteUrl(event.target.value)}
              placeholder="https://example.com"
              autoComplete="url"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="business_name">Business name</Label>
            <Input
              id="business_name"
              value={businessName}
              onChange={(event) => setBusinessName(event.target.value)}
              placeholder="Center Street Lending"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="business_type">Business type</Label>
            <Input
              id="business_type"
              value={businessType}
              onChange={(event) => setBusinessType(event.target.value)}
              placeholder="Hard money lender"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="city">City / service area</Label>
            <Input
              id="city"
              value={city}
              onChange={(event) => setCity(event.target.value)}
              placeholder="California"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="scan_mode">Scan depth</Label>
            <select
              id="scan_mode"
              value={scanMode}
              onChange={(event) => setScanMode(event.target.value)}
              className="h-11 w-full rounded-md border border-slate-200 bg-white px-3 text-sm shadow-sm"
            >
              <option value="basic">Basic — up to 25 pages</option>
              <option value="quick">Quick — up to 75 pages</option>
              <option value="deep">Deep — up to 200 pages</option>
              <option value="advanced">Advanced — up to 350 pages</option>
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="country">Country</Label>
            <Input
              id="country"
              value={country}
              onChange={(event) => setCountry(event.target.value)}
              placeholder="us"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="language">Language</Label>
            <Input
              id="language"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              placeholder="en"
            />
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <Label>Competitor URLs</Label>
            <p className="mt-1 text-xs text-slate-500">
              Manual competitor URLs work without SerpAPI. These are sent as{" "}
              <code>competitor_urls</code> to the scanner.
            </p>
          </div>

          {competitorUrls.map((url, index) => (
            <Input
              key={index}
              value={url}
              onChange={(event) =>
                updateCompetitorUrl(index, event.target.value)
              }
              placeholder={`Competitor ${index + 1}`}
              autoComplete="url"
            />
          ))}
        </div>

        {error ? (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-none" />
            <span>{error}</span>
          </div>
        ) : null}

        {visibleWarnings.length > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            {visibleWarnings.map((warning, index) => (
              <div key={index}>{warning}</div>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={loading}>
            {loading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : null}
            {loading ? "Scanning..." : "Scan Website"}
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={() => setShowDebug((current) => !current)}
          >
            <Bug className="mr-2 h-4 w-4" />
            {showDebug ? "Hide debug" : "Show debug"}
          </Button>
        </div>
      </form>

      {finalResult ? (
        <div className="space-y-4 rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-1 h-5 w-5 text-green-600" />
            <div>
              <h3 className="text-xl font-semibold text-slate-950">
                Scan complete
              </h3>
              <p className="mt-1 text-sm text-slate-600">{finalSummary}</p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Pages scanned" value={finalPages.length} />
            <Metric label="Recommendations" value={finalFixes.length} />
            <Metric
              label="Technical issues"
              value={finalResult?.scan_summary?.technical_issue_count || 0}
            />
            <Metric
              label="Competitor insights"
              value={finalResult?.competitor_insights?.length || 0}
            />
          </div>

          {reviewResult?.ai_review_warning ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {reviewResult.ai_review_warning}
            </div>
          ) : null}

          <div className="space-y-3">
            {finalFixes.slice(0, 12).map((fix) => (
              <div
                key={fix.id || fix.fix_id || fix.issue_title}
                className="rounded-xl border p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                    {fix.priority || "medium"}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                    {fix.customer_category ||
                      fix.category ||
                      "Website improvement"}
                  </span>
                </div>

                <h4 className="mt-3 font-semibold text-slate-950">
                  {fix.issue_title || fix.title}
                </h4>

                <p className="mt-1 text-sm text-slate-600">
                  {fix.plain_english_explanation || fix.summary}
                </p>

                {Array.isArray(fix.affected_pages) &&
                fix.affected_pages.length > 0 ? (
                  <p className="mt-2 text-xs text-slate-500">
                    Affected pages: {fix.affected_pages.slice(0, 5).join(", ")}
                    {fix.affected_pages.length > 5 ? "…" : ""}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {showDebug ? (
        <div className="rounded-2xl border bg-slate-950 p-4 text-xs text-slate-100 shadow-sm">
          <div className="mb-2 font-semibold">Debug output</div>

          <pre className="max-h-[600px] overflow-auto whitespace-pre-wrap">
            {JSON.stringify(
              {
                error,
                functions: {
                  scanner: ADVANCED_SCANNER_FUNCTION,
                  ai_review: AI_REVIEW_FUNCTION,
                },
                scanner: {
                  pages: scanResult?.crawled_pages?.length || 0,
                  fixes: scanResult?.raw_fixes?.length || 0,
                  grouped_findings: scanResult?.grouped_findings?.length || 0,
                  raw_findings: scanResult?.raw_findings?.length || 0,

                  normalized_url: scanResult?.normalized_url || "",
                  domain: scanResult?.domain || "",
                  pages_found: scanResult?.pages_found || 0,
                  pages_crawled: scanResult?.pages_crawled || 0,
                  queued_remaining: scanResult?.queued_remaining || 0,

                  screaming_frog_lite_enabled:
                    scanResult?.screaming_frog_lite_enabled || false,
                  audit_profile: scanResult?.audit_profile || "",
                  technical_audit_summary:
                    scanResult?.technical_audit_summary || null,

                  competitor_urls_returned: scanResult?.competitor_urls || [],
                  competitor_results:
                    scanResult?.competitor_results?.length || 0,
                  competitor_page_snapshots:
                    scanResult?.competitor_page_snapshots?.length || 0,
                  competitor_comparison_exists: Boolean(
                    scanResult?.competitor_comparison
                  ),

                  first_competitor_results: (
                    scanResult?.competitor_results || []
                  ).slice(0, 5),

                  first_competitor_snapshots: (
                    scanResult?.competitor_page_snapshots || []
                  )
                    .slice(0, 3)
                    .map((item) => ({
                      competitor_name: item.competitor_name,
                      competitor_domain: item.competitor_domain,
                      competitor_url: item.competitor_url,
                      status_code: item.status_code,
                      title: item.title,
                      word_count: item.word_count,
                      fetch_error: item.fetch_error,
                    })),

                  client_rendering: scanResult?.client_rendering || null,

                  first_pages: (scanResult?.crawled_pages || [])
                    .slice(0, 10)
                    .map((page) => ({
                      url: page.url,
                      status_code: page.status_code,
                      title: page.title,
                      word_count: page.word_count,
                      internal_links: page.internal_links?.length || 0,
                      likely_client_rendered: page.likely_client_rendered,
                      fetch_error: page.fetch_error,
                    })),

                  crawl_warnings: scanResult?.crawl_warnings || [],
                  error: scanResult?.error || "",
                },
                ai_review: {
                  pages: reviewResult?.crawled_pages?.length || 0,
                  fixes: reviewResult?.raw_fixes?.length || 0,
                  cleaned_fixes: reviewResult?.cleaned_fixes?.length || 0,
                  recommended_actions:
                    reviewResult?.recommended_actions?.length || 0,
                  error: reviewResult?.error || "",
                  warning: reviewResult?.ai_review_warning || "",
                },
                final: {
                  pages: finalPages.length,
                  fixes: finalFixes.length,
                  competitor_insights:
                    finalResult?.competitor_insights?.length || 0,
                },
              },
              null,
              2
            )}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-xl border bg-slate-50 p-4">
      <div className="text-2xl font-semibold text-slate-950">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

async function callBase44Function(functionName, payload) {
  console.log("CALLING BASE44 FUNCTION", {
    functionName,
    payload,
    availableBase44Keys: base44 ? Object.keys(base44) : [],
    availableFunctionKeys: base44?.functions
      ? Object.keys(base44.functions)
      : [],
  });

  if (!base44) {
    throw new Error("base44 client is not available.");
  }

  try {
    if (base44.functions?.invoke) {
      const response = await base44.functions.invoke(functionName, payload);
      console.log("BASE44 FUNCTION RESPONSE", { functionName, response });
      return response;
    }

    if (base44.functions?.[functionName]) {
      const response = await base44.functions[functionName](payload);
      console.log("BASE44 DIRECT FUNCTION RESPONSE", {
        functionName,
        response,
      });
      return response;
    }

    if (base44.integrations?.Core?.InvokeFunction) {
      const response = await base44.integrations.Core.InvokeFunction({
        name: functionName,
        body: payload,
      });
      console.log("BASE44 CORE FUNCTION RESPONSE", {
        functionName,
        response,
      });
      return response;
    }

    throw new Error(
      `Could not find a Base44 function caller. Available base44 keys: ${Object.keys(
        base44 || {}
      ).join(", ")}`
    );
  } catch (error) {
    console.error("BASE44 FUNCTION CALL FAILED", {
      functionName,
      payload,
      message: error?.message,
      status: error?.response?.status || error?.status,
      responseData: error?.response?.data,
      fullError: error,
    });

    throw new Error(extractFunctionErrorMessage(error, functionName));
  }
}

function extractFunctionErrorMessage(error, functionName) {
  const responseData = error?.response?.data || error?.data || error?.body || null;

  if (typeof responseData === "string" && responseData.trim()) {
    return `${functionName} failed: ${responseData}`;
  }

  const backendMessage =
    responseData?.error ||
    responseData?.message ||
    error?.message ||
    "Unknown backend error.";

  const status = error?.response?.status || error?.status;

  if (status) {
    return `${functionName} failed with status ${status}: ${backendMessage}`;
  }

  return `${functionName} failed: ${backendMessage}`;
}

function unwrapFunctionResponse(response) {
  if (!response) return {};

  if (typeof response === "string") {
    try {
      return JSON.parse(response);
    } catch {
      return { raw_response: response };
    }
  }

  if (response.data?.data) return response.data.data;
  if (response.data?.result) return response.data.result;
  if (response.data) return response.data;
  if (response.result?.data) return response.result.data;
  if (response.result) return response.result;

  return response;
}

function normalizeScanResult(result) {
  const pages = pickFirstNonEmptyArray([
    result.crawled_pages,
    result.pages,
    result.scanned_pages,
    result.crawl_pages,
  ]);

  const fixes = pickFirstNonEmptyArray([
    result.raw_fixes,
    result.grouped_findings,
    result.raw_findings,
    result.findings,
    result.fixes,
    result.recommendations,
    result.issues,
  ]).map(normalizeFixForDisplay);

  return {
    ...result,

    crawled_pages: pages,
    pages,

    raw_fixes: fixes,
    fixes,
    findings: fixes,
    recommendations: fixes,

    grouped_findings: Array.isArray(result.grouped_findings)
      ? result.grouped_findings
      : fixes,

    raw_findings: Array.isArray(result.raw_findings)
      ? result.raw_findings
      : fixes,

    competitor_results: Array.isArray(result.competitor_results)
      ? result.competitor_results
      : [],

    competitor_page_snapshots: Array.isArray(result.competitor_page_snapshots)
      ? result.competitor_page_snapshots
      : [],

    crawl_warnings: Array.isArray(result.crawl_warnings)
      ? result.crawl_warnings
      : [],
  };
}

function normalizeReviewResult(result, scanner) {
  const fixes = pickFirstNonEmptyArray([
    result.cleaned_fixes,
    result.raw_fixes,
    result.fixes,
    result.findings,
    result.recommendations,
  ]).map(normalizeFixForDisplay);

  const pages = pickFirstNonEmptyArray([
    result.crawled_pages,
    result.pages,
    scanner?.crawled_pages,
    scanner?.pages,
  ]);

  return {
    ...result,

    cleaned_fixes: fixes,
    raw_fixes: fixes,
    fixes,
    findings: fixes,
    recommendations: fixes,

    crawled_pages: pages,
    pages,

    recommended_actions: Array.isArray(result.recommended_actions)
      ? result.recommended_actions
      : [],

    top_recommended_actions: Array.isArray(result.top_recommended_actions)
      ? result.top_recommended_actions
      : [],

    competitor_insights: Array.isArray(result.competitor_insights)
      ? result.competitor_insights
      : [],
  };
}

function normalizeFixForDisplay(fix, index = 0) {
  if (!fix || typeof fix !== "object") {
    return {
      id: `fix_${index}`,
      fix_id: `fix_${index}`,
      issue_title: String(fix || "Recommendation"),
      title: String(fix || "Recommendation"),
      priority: "medium",
      customer_category: "Website improvement",
      plain_english_explanation: "Review this recommendation.",
      affected_pages: [],
    };
  }

  const id = fix.id || fix.fix_id || `fix_${index}`;

  return {
    ...fix,

    id,
    fix_id: id,

    issue_title:
      fix.issue_title || fix.title || fix.headline || "Recommendation",

    title: fix.title || fix.issue_title || fix.headline || "Recommendation",

    priority: fix.priority || "medium",

    customer_category:
      fix.customer_category || fix.category || "Website improvement",

    plain_english_explanation:
      fix.plain_english_explanation ||
      fix.plain_english_summary ||
      fix.explanation ||
      fix.summary ||
      fix.description ||
      "Review this recommendation.",

    affected_pages: Array.isArray(fix.affected_pages)
      ? fix.affected_pages
      : fix.page_url
        ? [fix.page_url]
        : [],
  };
}

function pickFirstNonEmptyArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }

  return [];
}