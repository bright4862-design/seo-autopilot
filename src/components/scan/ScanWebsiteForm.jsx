import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, AlertCircle, CheckCircle2, Bug } from "lucide-react";
import { base44 } from "@/api/base44Client";

const ADVANCED_SCANNER_FUNCTION = "runAdvancedScan";
const AI_REVIEW_FUNCTION = "runAiReview";

const SCAN_STEPS = [
  "Finding pages",
  "Reading sitemap",
  "Reading website content",
  "Checking internal links",
  "Finding competitor pages",
  "Comparing competitors",
  "Preparing recommendations",
  "Complete",
];

function getArray(...values) {
  for (const value of values) {
    if (Array.isArray(value) && value.length > 0) return value;
  }

  return [];
}

function unwrapFunctionResponse(response) {
  if (!response) return {};

  if (response.data?.data) return response.data.data;
  if (response.data?.result) return response.data.result;
  if (response.data) return response.data;
  if (response.result?.data) return response.result.data;
  if (response.result) return response.result;

  return response;
}

function ensureProtocol(url) {
  const clean = String(url || "").trim();

  if (!clean) return "";
  if (/^https?:\/\//i.test(clean)) return clean;

  return `https://${clean}`;
}

function getDomain(url) {
  try {
    return new URL(ensureProtocol(url)).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function normalizePriority(priority) {
  const value = String(priority || "").toLowerCase();

  if (value === "critical") return "critical";
  if (value === "high") return "high";
  if (value === "medium") return "medium";
  if (value === "low") return "low";

  return "medium";
}

function normalizeFixStatus(fix) {
  if (fix.status) return fix.status;

  if (fix.requires_developer) return "needs_developer";
  if (fix.requires_approval) return "needs_approval";
  if (fix.can_auto_fix) return "auto_fixed";

  return "needs_approval";
}

function normalizeFix(fix, index = 0) {
  const title =
    fix.issue_title ||
    fix.title ||
    fix.headline ||
    "Recommended improvement";

  const id =
    fix.id ||
    fix.fix_id ||
    `fix_${index}_${String(title)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")}`;

  const status = normalizeFixStatus(fix);

  return {
    ...fix,
    id,
    fix_id: id,
    status,
    priority: normalizePriority(fix.priority),

    issue_title: title,
    title,

    plain_english_explanation:
      fix.plain_english_explanation ||
      fix.plain_english_summary ||
      fix.summary ||
      fix.description ||
      "This improvement was found during the website scan.",

    why_it_matters:
      fix.why_it_matters ||
      fix.reason ||
      fix.why ||
      "Improving this can make the website clearer for visitors and search engines.",

    current_value:
      fix.current_value ||
      fix.current ||
      fix.technical_detail ||
      "",

    recommended_value:
      fix.recommended_value ||
      fix.recommendation ||
      fix.recommended_action ||
      fix.ai_recommendation ||
      "Review this recommendation.",

    what_to_do:
      Array.isArray(fix.what_to_do)
        ? fix.what_to_do
        : Array.isArray(fix.what_to_do_steps)
          ? fix.what_to_do_steps
          : Array.isArray(fix.fix_steps)
            ? fix.fix_steps
            : [],

    affected_pages:
      Array.isArray(fix.affected_pages)
        ? fix.affected_pages
        : Array.isArray(fix.pages)
          ? fix.pages
          : fix.page_url
            ? [fix.page_url]
            : [],

    customer_category:
      fix.customer_category ||
      fix.category ||
      fix.type ||
      "Website improvement",

    who_can_do_this:
      fix.who_can_do_this === "your_web_person"
        ? "Your web person"
        : fix.who_can_do_this || "You or your web person",

    estimated_time:
      fix.estimated_time ||
      fix.time_estimate ||
      "About 30–60 minutes",
  };
}

function calculateScore(fixes) {
  let score = 100;

  for (const fix of fixes || []) {
    if (fix.priority === "critical") score -= 16;
    else if (fix.priority === "high") score -= 10;
    else if (fix.priority === "medium") score -= 5;
    else if (fix.priority === "low") score -= 2;
  }

  return Math.max(0, Math.min(100, score));
}

function normalizeScanResult(rawResponse) {
  const data = unwrapFunctionResponse(rawResponse);

  const pages = getArray(
    data.crawled_pages,
    data.pages,
    data.scanned_pages,
    data.crawl_pages
  );

  const fixes = getArray(
    data.cleaned_fixes,
    data.raw_fixes,
    data.grouped_findings,
    data.raw_findings,
    data.findings,
    data.fixes,
    data.recommendations,
    data.issues
  ).map(normalizeFix);

  const competitorInsights = getArray(
    data.competitor_insights,
    data.competitorInsights,
    data.competitor_gaps
  );

  const score =
    typeof data.health_score === "number"
      ? data.health_score
      : typeof data.scan_summary?.score === "number"
        ? data.scan_summary.score
        : calculateScore(fixes);

  return {
    ...data,

    success: data.success !== false,
    error: data.error || "",

    pages,
    crawled_pages: pages,
    pages_crawled:
      data.pages_crawled ||
      data.pages_scanned ||
      data.scan_summary?.pages_scanned ||
      pages.length,

    raw_fixes: fixes,
    fixes,
    findings: fixes,
    recommendations: fixes,

    recommended_actions: getArray(
      data.recommended_actions,
      data.top_recommended_actions
    ),

    competitor_insights: competitorInsights,

    health_score: score,

    scan_summary: {
      score,
      status_label:
        data.scan_summary?.status_label ||
        (score >= 80
          ? "Strong"
          : score >= 60
            ? "Good start"
            : score >= 40
              ? "Needs work"
              : "Needs urgent attention"),

      plain_english_summary:
        data.scan_summary?.plain_english_summary ||
        data.plain_english_summary ||
        data.site_summary?.plain_english_summary ||
        "The scan completed. Review the recommended improvements below.",

      pages_scanned:
        data.scan_summary?.pages_scanned ||
        data.pages_crawled ||
        pages.length,

      pages_failed:
        data.scan_summary?.pages_failed ||
        data.failed_pages ||
        data.crawl_failed ||
        0,

      high_priority_count:
        data.scan_summary?.high_priority_count ||
        fixes.filter((fix) =>
          ["critical", "high"].includes(fix.priority)
        ).length,

      competitor_gap_count:
        data.scan_summary?.competitor_gap_count ||
        competitorInsights.length ||
        fixes.filter(
          (fix) =>
            fix.category === "competitor_gap" ||
            fix.customer_category === "Competitor opportunities"
        ).length,
    },

    debug_raw_response: rawResponse,
    debug_unwrapped: data,
  };
}

function extractFunctionErrorMessage(error, functionName) {
  const responseData =
    error?.response?.data ||
    error?.data ||
    error?.body ||
    null;

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

      console.log("BASE44 FUNCTION RESPONSE", {
        functionName,
        response,
      });

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

function statusCounts(fixes) {
  const prepared = fixes.filter((fix) => fix.status === "auto_fixed").length;

  const needsReview = fixes.filter(
    (fix) =>
      fix.status === "needs_approval" ||
      (!fix.requires_developer && fix.status !== "auto_fixed")
  ).length;

  const mayNeedHelp = fixes.filter(
    (fix) =>
      fix.status === "needs_developer" ||
      fix.requires_developer ||
      fix.who_can_do_this === "Your web person" ||
      fix.who_can_do_this === "your_web_person"
  ).length;

  return {
    prepared,
    needsReview,
    mayNeedHelp,
  };
}

function StepCircle({ complete, active, children }) {
  return (
    <div
      className={[
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-bold",
        complete
          ? "border-slate-950 bg-slate-950 text-white"
          : active
            ? "border-blue-600 bg-blue-600 text-white"
            : "border-slate-300 bg-white text-slate-400",
      ].join(" ")}
    >
      {complete ? "✓" : children}
    </div>
  );
}

function priorityClass(priority) {
  if (priority === "critical" || priority === "high") {
    return "border-red-200 bg-red-50 text-red-700";
  }

  if (priority === "medium") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }

  return "border-slate-200 bg-slate-50 text-slate-700";
}

function FixPreview({ fix }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="mb-2 flex flex-wrap gap-2">
        <span
          className={[
            "rounded-full border px-2.5 py-1 text-xs font-semibold",
            priorityClass(fix.priority),
          ].join(" ")}
        >
          {fix.priority}
        </span>

        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-600">
          {fix.customer_category}
        </span>
      </div>

      <h3 className="text-base font-bold text-slate-950">
        {fix.issue_title}
      </h3>

      <p className="mt-2 text-sm leading-6 text-slate-600">
        {fix.plain_english_explanation}
      </p>

      {fix.affected_pages?.length ? (
        <p className="mt-3 text-xs text-slate-400">
          {fix.affected_pages.length} affected page
          {fix.affected_pages.length === 1 ? "" : "s"}
        </p>
      ) : null}
    </div>
  );
}

export default function ScanWebsiteForm({
  project,
  competitors = [],
  savedCompetitors = [],
  onScanComplete,
  onComplete,
  onFinished,
}) {
  const [businessName, setBusinessName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [keywords, setKeywords] = useState("");
  const [competitorUrls, setCompetitorUrls] = useState(["", "", ""]);
  const [scanDepth, setScanDepth] = useState("quick");

  const [isScanning, setIsScanning] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [scanComplete, setScanComplete] = useState(false);
  const [error, setError] = useState("");

  const [scanResult, setScanResult] = useState(null);
  const [reviewResult, setReviewResult] = useState(null);
  const [showDebug, setShowDebug] = useState(false);

  useEffect(() => {
    if (project) {
      setBusinessName(project.business_name || "");
      setWebsiteUrl(project.website_url || "");
      setKeywords((project.important_keywords || []).join(", "));
    }
  }, [project]);

  useEffect(() => {
    const allCompetitors = competitors.length ? competitors : savedCompetitors;

    if (allCompetitors.length > 0) {
      setCompetitorUrls(
        [0, 1, 2].map(
          (index) =>
            allCompetitors[index]?.website_url ||
            allCompetitors[index]?.url ||
            ""
        )
      );
    }
  }, [competitors, savedCompetitors]);

  const finalResult = reviewResult || scanResult;
  const finalPages = finalResult?.crawled_pages || [];
  const finalFixes = finalResult?.raw_fixes || [];
  const counts = statusCounts(finalFixes);
  const domainPreview = useMemo(() => getDomain(websiteUrl), [websiteUrl]);

  const canSubmit =
    businessName.trim().length > 0 && websiteUrl.trim().length > 0;

  async function handleSubmit(event) {
    event.preventDefault();

    const url = ensureProtocol(websiteUrl);

    if (!url) {
      setError("Enter a website URL before running the scan.");
      return;
    }

    setIsScanning(true);
    setScanComplete(false);
    setError("");
    setScanResult(null);
    setReviewResult(null);
    setShowDebug(false);
    setActiveStep(0);

    const stepTimer = window.setInterval(() => {
      setActiveStep((step) => Math.min(step + 1, SCAN_STEPS.length - 2));
    }, 1300);

    try {
      const keywordList = keywords
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);

      const competitorUrlList = competitorUrls
        .map((item) => item.trim())
        .filter(Boolean);

      const scannerPayload = {
        website_url: url,
        business_name: businessName,
        business_type:
          project?.business_type ||
          project?.industry ||
          project?.niche ||
          "",
        city:
          project?.city ||
          project?.location ||
          project?.service_area ||
          "",
        country: project?.country || "us",
        language: project?.language || "en",
        project_id: project?.id || "",
        scan_mode: scanDepth,
        important_keywords: keywordList,
        competitor_urls: competitorUrlList,
      };

      const scannerRaw = await callBase44Function(
        ADVANCED_SCANNER_FUNCTION,
        scannerPayload
      );

      const scanner = normalizeScanResult(scannerRaw);

      console.log("ADVANCED SCAN DEBUG", {
        raw: scannerRaw,
        normalized: scanner,
        success: scanner.success,
        error: scanner.error,
        pages: scanner.crawled_pages.length,
        fixes: scanner.raw_fixes.length,
        grouped_findings: scanner.grouped_findings?.length,
        raw_findings: scanner.raw_findings?.length,
        crawl_warnings: scanner.crawl_warnings,
      });

      if (!scanner.success) {
        throw new Error(scanner.error || "runAdvancedScan failed.");
      }

      setScanResult(scanner);
      setActiveStep(6);

      if (scanner.crawled_pages.length === 0) {
        throw new Error(
          "runAdvancedScan returned zero pages. Open Show debug and browser console to inspect the scanner response."
        );
      }

      const aiPayload = {
        website_url: scanner.normalized_url || scanner.website_url || url,
        normalized_url: scanner.normalized_url || url,

        business_name: businessName,
        business_type:
          project?.business_type ||
          project?.industry ||
          project?.niche ||
          "",
        city:
          project?.city ||
          project?.location ||
          project?.service_area ||
          "",

        crawled_pages: scanner.crawled_pages,
        pages: scanner.crawled_pages,

        raw_fixes: scanner.raw_fixes,
        grouped_findings: scanner.grouped_findings || scanner.raw_fixes,
        raw_findings: scanner.raw_findings || scanner.raw_fixes,
        findings: scanner.raw_fixes,
        fixes: scanner.raw_fixes,
        recommendations: scanner.raw_fixes,

        competitor_page_snapshots:
          scanner.competitor_page_snapshots || [],
        competitor_comparison:
          scanner.competitor_comparison || null,
        client_rendering:
          scanner.client_rendering || null,
        crawl_warnings:
          scanner.crawl_warnings || [],
        scan_mode:
          scanner.scan_mode || scanDepth,
        health_score:
          scanner.health_score,
      };

      let finalReview = null;

      try {
        const aiRaw = await callBase44Function(AI_REVIEW_FUNCTION, aiPayload);
        const review = normalizeScanResult(aiRaw);

        console.log("AI REVIEW DEBUG", {
          raw: aiRaw,
          normalized: review,
          success: review.success,
          error: review.error,
          pages: review.crawled_pages.length,
          fixes: review.raw_fixes.length,
          cleaned_fixes: review.cleaned_fixes?.length,
          recommended_actions: review.recommended_actions?.length,
          competitor_insights: review.competitor_insights?.length,
        });

        if (review.success && review.raw_fixes.length > 0) {
          finalReview = review;
          setReviewResult(review);
        } else {
          finalReview = {
            ...scanner,
            ai_review_warning:
              review.error ||
              review.ai_review_warning ||
              "AI review returned no fixes, so scanner recommendations are shown.",
          };

          setReviewResult(finalReview);
        }
      } catch (aiError) {
        console.warn("AI REVIEW FAILED, USING SCANNER RESULTS", aiError);

        finalReview = {
          ...scanner,
          ai_review_warning:
            aiError?.message ||
            "AI review failed, so scanner recommendations are shown.",
        };

        setReviewResult(finalReview);
      }

      const finalPayload = finalReview || scanner;

      setActiveStep(SCAN_STEPS.length - 1);
      setScanComplete(true);

      if (typeof onScanComplete === "function") onScanComplete(finalPayload);
      if (typeof onComplete === "function") onComplete(finalPayload);
      if (typeof onFinished === "function") onFinished(finalPayload);
    } catch (err) {
      console.error("SCAN WEBSITE FORM ERROR", err);
      setError(err?.message || "The scan failed.");
    } finally {
      window.clearInterval(stepTimer);
      setIsScanning(false);
      setActiveStep(SCAN_STEPS.length - 1);
    }
  }

  return (
    <div className="space-y-8">
      <form
        onSubmit={handleSubmit}
        className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm"
      >
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-slate-950">
            Scan your website
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            We’ll crawl your site, compare competitor pages, and prepare SEO
            recommendations.
          </p>
        </div>

        <div className="grid gap-5">
          <div>
            <Label htmlFor="businessName">Business name</Label>
            <Input
              id="businessName"
              value={businessName}
              onChange={(event) => setBusinessName(event.target.value)}
              placeholder="Your business name"
              className="mt-2"
            />
          </div>

          <div>
            <Label htmlFor="websiteUrl">Website URL</Label>
            <Input
              id="websiteUrl"
              value={websiteUrl}
              onChange={(event) => setWebsiteUrl(event.target.value)}
              placeholder="example.com"
              className="mt-2"
            />
            {domainPreview ? (
              <p className="mt-2 text-xs text-slate-400">
                Scanner target:{" "}
                <span className="font-semibold">{domainPreview}</span>
              </p>
            ) : null}
          </div>

          <div>
            <Label htmlFor="keywords">Important keywords</Label>
            <Input
              id="keywords"
              value={keywords}
              onChange={(event) => setKeywords(event.target.value)}
              placeholder="keyword one, keyword two"
              className="mt-2"
            />
          </div>

          <div>
            <Label>Competitor URLs</Label>
            <div className="mt-2 grid gap-3">
              {competitorUrls.map((url, index) => (
                <Input
                  key={index}
                  value={url}
                  onChange={(event) => {
                    const next = [...competitorUrls];
                    next[index] = event.target.value;
                    setCompetitorUrls(next);
                  }}
                  placeholder={`Competitor ${index + 1}`}
                />
              ))}
            </div>
          </div>

          <div>
            <Label htmlFor="scanDepth">Scan depth</Label>
            <select
              id="scanDepth"
              value={scanDepth}
              onChange={(event) => setScanDepth(event.target.value)}
              className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="basic">Basic</option>
              <option value="quick">Quick</option>
              <option value="deep">Deep</option>
            </select>
          </div>
        </div>

        {error ? (
          <div className="mt-5 flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{error}</p>
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap gap-3">
          <Button type="submit" disabled={!canSubmit || isScanning}>
            {isScanning ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Scanning...
              </>
            ) : (
              "Run scan"
            )}
          </Button>

          {(finalResult || error) ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => setShowDebug(!showDebug)}
            >
              <Bug className="mr-2 h-4 w-4" />
              {showDebug ? "Hide debug" : "Show debug"}
            </Button>
          ) : null}
        </div>
      </form>

      {(isScanning || scanComplete || error) && (
        <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="space-y-5">
            {SCAN_STEPS.map((step, index) => {
              const complete = scanComplete || index < activeStep;
              const active = !scanComplete && index === activeStep;

              return (
                <div key={step} className="flex items-center gap-4">
                  <StepCircle complete={complete} active={active}>
                    {index + 1}
                  </StepCircle>
                  <p className="text-base font-semibold text-slate-950">
                    {step}
                  </p>
                </div>
              );
            })}
          </div>

          <p className="mt-7 text-sm leading-6 text-slate-400">
            This scan reviews website content we can access directly. Some
            websites may need a deeper manual review.
          </p>
        </div>
      )}

      {finalResult ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-1 h-5 w-5 text-emerald-600" />
            <div>
              <h2 className="text-2xl font-bold text-slate-950">
                Your scan is complete.
              </h2>
              <p className="mt-3 text-base leading-7 text-slate-600">
                We reviewed{" "}
                <span className="font-bold text-slate-950">
                  {finalPages.length}
                </span>{" "}
                pages and prepared{" "}
                <span className="font-bold text-slate-950">
                  {finalFixes.length}
                </span>{" "}
                recommended improvements.
              </p>
            </div>
          </div>

          {finalResult.ai_review_warning ? (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
              {finalResult.ai_review_warning}
            </div>
          ) : null}

          <div className="mt-6 grid gap-4 md:grid-cols-4">
            <div className="rounded-2xl bg-slate-50 p-5">
              <p className="text-3xl font-bold text-slate-950">
                {finalResult.health_score}
              </p>
              <p className="mt-1 text-sm text-slate-500">SEO score</p>
            </div>

            <div className="rounded-2xl bg-slate-50 p-5">
              <p className="text-3xl font-bold text-slate-950">
                {counts.prepared}
              </p>
              <p className="mt-1 text-sm text-slate-500">Prepared</p>
            </div>

            <div className="rounded-2xl bg-slate-50 p-5">
              <p className="text-3xl font-bold text-slate-950">
                {counts.needsReview}
              </p>
              <p className="mt-1 text-sm text-slate-500">Needs review</p>
            </div>

            <div className="rounded-2xl bg-slate-50 p-5">
              <p className="text-3xl font-bold text-slate-950">
                {counts.mayNeedHelp}
              </p>
              <p className="mt-1 text-sm text-slate-500">May need help</p>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/fix-list"
              className="inline-flex items-center rounded-full bg-blue-600 px-6 py-3 text-sm font-bold text-white hover:bg-blue-700"
            >
              View Fix List
            </Link>
          </div>

          {finalFixes.length === 0 ? (
            <p className="mt-6 text-sm leading-6 text-slate-500">
              No major recommendations found based on the website content we
              could access. Open debug below to check whether the scanner
              returned pages or grouped findings.
            </p>
          ) : (
            <div className="mt-8 space-y-4">
              <h3 className="text-lg font-bold text-slate-950">
                Recommendations found
              </h3>
              {finalFixes.slice(0, 5).map((fix) => (
                <FixPreview key={fix.id} fix={fix} />
              ))}
            </div>
          )}
        </div>
      ) : null}

      {showDebug ? (
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 bg-slate-50 p-5">
            <h2 className="text-lg font-bold text-slate-950">
              Debug output
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Use this to confirm whether the scanner returned pages and fixes.
            </p>
          </div>

          <pre className="max-h-[600px] overflow-auto bg-slate-950 p-5 text-xs leading-5 text-slate-100">
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
                  grouped_findings:
                    scanResult?.grouped_findings?.length || 0,
                  raw_findings:
                    scanResult?.raw_findings?.length || 0,
                  error: scanResult?.error || "",
                  crawl_warnings: scanResult?.crawl_warnings || [],
                },
                ai_review: {
                  pages: reviewResult?.crawled_pages?.length || 0,
                  fixes: reviewResult?.raw_fixes?.length || 0,
                  cleaned_fixes:
                    reviewResult?.cleaned_fixes?.length || 0,
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