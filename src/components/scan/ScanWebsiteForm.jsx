import React, { useMemo, useState } from "react";
import {
  AlertCircle,
  Bug,
  CheckCircle2,
  ExternalLink,
  HeartPulse,
  Loader2,
  Search,
  Sparkles,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { base44 } from "@/api/base44Client";

const ADVANCED_SCANNER_FUNCTION = "runAdvancedScan";
const AI_REVIEW_FUNCTION = "aiReviewScan";
const DEFAULT_COMPETITOR_FIELDS = ["", "", ""];

const DASHBOARD_LAST_SCAN_KEY = "seo_autopilot:last_scan";
const DASHBOARD_HISTORY_KEY = "seo_autopilot:scan_history";

export default function ScanWebsiteForm() {
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("us");
  const [language, setLanguage] = useState("en");
  const [scanMode, setScanMode] = useState("deep");
  const [competitorUrls, setCompetitorUrls] = useState(
    DEFAULT_COMPETITOR_FIELDS
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [scanResult, setScanResult] = useState(null);
  const [reviewResult, setReviewResult] = useState(null);
  const [finalResult, setFinalResult] = useState(null);

  const [showDebug, setShowDebug] = useState(false);

  const cleanedCompetitorUrls = useMemo(() => {
    return competitorUrls
      .map((url) => String(url || "").trim())
      .filter(Boolean);
  }, [competitorUrls]);

  const displayResult = finalResult || reviewResult || scanResult || {};

  const fixes = useMemo(() => {
    return pickFirstNonEmptyArray([
      displayResult.cleaned_fixes,
      displayResult.fixes,
      displayResult.findings,
      displayResult.recommendations,
      displayResult.raw_fixes,
      scanResult?.raw_fixes,
      scanResult?.fixes,
    ]);
  }, [displayResult, scanResult]);

  const pages = useMemo(() => {
    return pickFirstNonEmptyArray([
      displayResult.crawled_pages,
      displayResult.pages,
      scanResult?.crawled_pages,
      scanResult?.pages,
    ]);
  }, [displayResult, scanResult]);

  const healthReport =
    displayResult.website_health_report ||
    displayResult.scan_summary?.website_health_report ||
    displayResult.scan_summary ||
    null;

  const healthScore =
    numberOrNull(displayResult.health_score) ??
    numberOrNull(displayResult.scan_summary?.score) ??
    numberOrNull(scanResult?.health_score) ??
    null;

  const debugPayload = useMemo(() => {
    return {
      error,
      functions: {
        scanner: ADVANCED_SCANNER_FUNCTION,
        ai_review: AI_REVIEW_FUNCTION,
      },
      scanner: {
        scan_mode: scanResult?.scan_mode || "",
        pages: safeArray(scanResult?.pages || scanResult?.crawled_pages).length,
        fixes: safeArray(scanResult?.fixes || scanResult?.raw_fixes).length,
        grouped_findings: safeArray(scanResult?.grouped_findings).length,
        raw_findings: safeArray(scanResult?.raw_findings).length,
        normalized_url: scanResult?.normalized_url || "",
        domain: scanResult?.domain || "",
        pages_found: scanResult?.pages_found || 0,
        pages_crawled: scanResult?.pages_crawled || 0,
        queued_remaining: scanResult?.queued_remaining || 0,
        screaming_frog_lite_enabled:
          scanResult?.screaming_frog_lite_enabled || false,
        audit_profile: scanResult?.audit_profile || "",
        crawl_scope: scanResult?.crawl_scope || null,
        technical_audit_summary: scanResult?.technical_audit_summary || null,
        competitor_urls_returned: scanResult?.competitor_urls || [],
        competitor_results: safeArray(scanResult?.competitor_results).length,
        competitor_page_snapshots: safeArray(
          scanResult?.competitor_page_snapshots
        ).length,
        competitor_comparison_exists: Boolean(
          scanResult?.competitor_comparison
        ),
        first_competitor_results: safeArray(
          scanResult?.competitor_results
        ).slice(0, 5),
        first_competitor_snapshots: safeArray(
          scanResult?.competitor_page_snapshots
        )
          .slice(0, 5)
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
        first_pages: safeArray(scanResult?.pages || scanResult?.crawled_pages)
          .slice(0, 10)
          .map((page) => ({
            url: page.url,
            status_code: page.status_code,
            title: page.title,
            word_count: page.word_count,
            internal_links: page.internal_link_count,
            likely_client_rendered: page.likely_client_rendered,
            fetch_error: page.fetch_error,
          })),
        crawl_warnings: scanResult?.crawl_warnings || [],
        error: scanResult?.error || "",
      },
      ai_review: {
        pages: safeArray(reviewResult?.pages || reviewResult?.crawled_pages)
          .length,
        fixes: safeArray(reviewResult?.fixes || reviewResult?.raw_fixes).length,
        cleaned_fixes: safeArray(reviewResult?.cleaned_fixes).length,
        recommended_actions: safeArray(reviewResult?.recommended_actions).length,
        provider: reviewResult?.ai_provider || "",
        error: reviewResult?.error || "",
        warning: reviewResult?.ai_review_warning || "",
      },
      final: {
        pages: pages.length,
        fixes: fixes.length,
        competitor_insights: safeArray(displayResult.competitor_insights).length,
        health_score: healthScore,
      },
    };
  }, [
    error,
    scanResult,
    reviewResult,
    displayResult,
    fixes.length,
    pages.length,
    healthScore,
  ]);

  async function handleSubmit(event) {
    event.preventDefault();

    setLoading(true);
    setError("");
    setScanResult(null);
    setReviewResult(null);
    setFinalResult(null);

    try {
      const scannerPayload = {
        website_url: String(websiteUrl || "").trim(),
        business_name: String(businessName || "").trim(),
        business_type: String(businessType || "").trim(),
        city: String(city || "").trim(),
        country: String(country || "us").trim().toLowerCase(),
        language: String(language || "en").trim().toLowerCase(),
        scan_mode: scanMode,
        enable_screaming_frog_lite: true,

        force_internal_crawl: true,
        respect_robots_txt: false,

        competitor_urls: cleanedCompetitorUrls,
      };

      const scannerResponse = await callBase44Function(
        ADVANCED_SCANNER_FUNCTION,
        scannerPayload
      );

      const normalizedScanner = normalizeFunctionResponse(scannerResponse);

      setScanResult(normalizedScanner);

      if (normalizedScanner?.success === false) {
        throw new Error(
          normalizedScanner?.error ||
            "The scanner failed before the AI review could run."
        );
      }

      const aiPayload = {
        ...scannerPayload,

        website_url:
          normalizedScanner.normalized_url ||
          normalizedScanner.website_url ||
          scannerPayload.website_url,

        normalized_url:
          normalizedScanner.normalized_url || scannerPayload.website_url,

        domain: normalizedScanner.domain || "",

        crawled_pages:
          normalizedScanner.crawled_pages ||
          normalizedScanner.pages ||
          normalizedScanner.scanned_pages ||
          [],

        pages:
          normalizedScanner.pages ||
          normalizedScanner.crawled_pages ||
          normalizedScanner.scanned_pages ||
          [],

        raw_fixes:
          normalizedScanner.raw_fixes ||
          normalizedScanner.grouped_findings ||
          normalizedScanner.raw_findings ||
          normalizedScanner.fixes ||
          [],

        grouped_findings:
          normalizedScanner.grouped_findings ||
          normalizedScanner.raw_fixes ||
          normalizedScanner.fixes ||
          [],

        raw_findings:
          normalizedScanner.raw_findings ||
          normalizedScanner.raw_fixes ||
          normalizedScanner.fixes ||
          [],

        fixes:
          normalizedScanner.fixes ||
          normalizedScanner.raw_fixes ||
          normalizedScanner.grouped_findings ||
          [],

        scan_summary:
          normalizedScanner.scan_summary || normalizedScanner.site_summary || {},

        health_score: normalizedScanner.health_score,

        technical_audit_summary:
          normalizedScanner.technical_audit_summary || null,

        screaming_frog_lite_enabled:
          normalizedScanner.screaming_frog_lite_enabled || false,

        audit_profile: normalizedScanner.audit_profile || "",

        crawl_warnings: normalizedScanner.crawl_warnings || [],
        crawl_scope: normalizedScanner.crawl_scope || null,

        client_rendering: normalizedScanner.client_rendering || null,

        competitor_urls:
          normalizedScanner.competitor_urls || cleanedCompetitorUrls,
        competitor_results: normalizedScanner.competitor_results || [],
        competitor_page_snapshots:
          normalizedScanner.competitor_page_snapshots || [],
        competitor_comparison: normalizedScanner.competitor_comparison || null,

        pages_found: normalizedScanner.pages_found || 0,
        pages_crawled: normalizedScanner.pages_crawled || 0,
        queued_remaining: normalizedScanner.queued_remaining || 0,
      };

      let normalizedReview = null;

      try {
        const reviewResponse = await callBase44Function(
          AI_REVIEW_FUNCTION,
          aiPayload
        );

        normalizedReview = normalizeFunctionResponse(reviewResponse);

        setReviewResult(normalizedReview);
      } catch (aiError) {
        normalizedReview = {
          success: true,
          ai_provider: "frontend_fallback",
          ai_review_warning:
            aiError?.message ||
            "AI review failed, so scanner recommendations are shown.",
          cleaned_fixes: aiPayload.raw_fixes,
          fixes: aiPayload.raw_fixes,
          recommendations: aiPayload.raw_fixes,
          crawled_pages: aiPayload.crawled_pages,
          pages: aiPayload.pages,
          health_score: aiPayload.health_score,
          scan_summary: aiPayload.scan_summary,
          competitor_insights: [],
        };

        setReviewResult(normalizedReview);
      }

      const mergedFinal = {
        ...normalizedScanner,
        ...normalizedReview,

        crawled_pages:
          normalizedReview?.crawled_pages ||
          normalizedReview?.pages ||
          normalizedScanner?.crawled_pages ||
          normalizedScanner?.pages ||
          [],

        pages:
          normalizedReview?.pages ||
          normalizedReview?.crawled_pages ||
          normalizedScanner?.pages ||
          normalizedScanner?.crawled_pages ||
          [],

        cleaned_fixes:
          normalizedReview?.cleaned_fixes ||
          normalizedReview?.fixes ||
          normalizedScanner?.raw_fixes ||
          normalizedScanner?.fixes ||
          [],

        fixes:
          normalizedReview?.fixes ||
          normalizedReview?.cleaned_fixes ||
          normalizedScanner?.fixes ||
          normalizedScanner?.raw_fixes ||
          [],

        recommendations:
          normalizedReview?.recommendations ||
          normalizedReview?.fixes ||
          normalizedScanner?.recommendations ||
          normalizedScanner?.fixes ||
          [],

        health_score:
          normalizedReview?.health_score ??
          normalizedScanner?.health_score ??
          normalizedReview?.scan_summary?.score ??
          normalizedScanner?.scan_summary?.score,

        competitor_insights:
          normalizedReview?.competitor_insights ||
          normalizedScanner?.competitor_insights ||
          [],
      };

      saveScanForDashboard({
        result: mergedFinal,
        scannerPayload,
        normalizedScanner,
        normalizedReview,
      });

      setFinalResult(mergedFinal);
    } catch (err) {
      setError(err?.message || "Scan failed.");
    } finally {
      setLoading(false);
    }
  }

  function updateCompetitorUrl(index, value) {
    setCompetitorUrls((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? value : item))
    );
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleSubmit}
        className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div className="flex items-start gap-3">
          <div className="rounded-2xl bg-blue-50 p-3 text-blue-700">
            <Search className="h-5 w-5" />
          </div>

          <div>
            <h2 className="text-xl font-semibold text-slate-950">
              Scan a website
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Crawl the site, review technical setup, and create plain-English
              recommendations.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-5 md:grid-cols-2">
          <div className="md:col-span-2">
            <Label htmlFor="website_url">Website URL</Label>
            <Input
              id="website_url"
              value={websiteUrl}
              onChange={(event) => setWebsiteUrl(event.target.value)}
              placeholder="https://www.example.com/en"
              required
              className="mt-2"
            />
          </div>

          <div>
            <Label htmlFor="business_name">Business name</Label>
            <Input
              id="business_name"
              value={businessName}
              onChange={(event) => setBusinessName(event.target.value)}
              placeholder="Example Business"
              className="mt-2"
            />
          </div>

          <div>
            <Label htmlFor="business_type">Business type</Label>
            <Input
              id="business_type"
              value={businessType}
              onChange={(event) => setBusinessType(event.target.value)}
              placeholder="Activity booking, restaurant, dentist..."
              className="mt-2"
            />
          </div>

          <div>
            <Label htmlFor="city">City</Label>
            <Input
              id="city"
              value={city}
              onChange={(event) => setCity(event.target.value)}
              placeholder="Paris"
              className="mt-2"
            />
          </div>

          <div>
            <Label htmlFor="country">Country</Label>
            <Input
              id="country"
              value={country}
              onChange={(event) => setCountry(event.target.value)}
              placeholder="fr"
              className="mt-2"
            />
          </div>

          <div>
            <Label htmlFor="language">Language</Label>
            <select
              id="language"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
            >
              <option value="en">English</option>
              <option value="fr">French</option>
              <option value="nl">Dutch</option>
              <option value="es">Spanish</option>
              <option value="de">German</option>
              <option value="it">Italian</option>
              <option value="pt">Portuguese</option>
            </select>
          </div>

          <div>
            <Label htmlFor="scan_mode">Scan depth</Label>
            <select
              id="scan_mode"
              value={scanMode}
              onChange={(event) => setScanMode(event.target.value)}
              className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
            >
              <option value="basic">Basic</option>
              <option value="quick">Quick</option>
              <option value="deep">Deep</option>
              <option value="advanced">Advanced</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <Label>Competitor URLs</Label>
            <div className="mt-2 grid gap-3 md:grid-cols-3">
              {competitorUrls.map((url, index) => (
                <Input
                  key={index}
                  value={url}
                  onChange={(event) =>
                    updateCompetitorUrl(index, event.target.value)
                  }
                  placeholder={`Competitor ${index + 1}`}
                />
              ))}
            </div>
          </div>
        </div>

        {error ? (
          <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <div className="flex gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Scanning...
              </>
            ) : (
              <>
                <Search className="mr-2 h-4 w-4" />
                Start scan
              </>
            )}
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={() => setShowDebug((value) => !value)}
          >
            <Bug className="mr-2 h-4 w-4" />
            {showDebug ? "Hide debug" : "Show debug"}
          </Button>
        </div>
      </form>

      {displayResult && Object.keys(displayResult).length > 0 ? (
        <ResultsView
          result={displayResult}
          fixes={fixes}
          pages={pages}
          healthReport={healthReport}
          healthScore={healthScore}
        />
      ) : null}

      {showDebug ? (
        <div className="rounded-3xl border border-slate-200 bg-slate-950 p-5 text-slate-100 shadow-sm">
          <div className="mb-3 flex items-center gap-2">
            <Bug className="h-4 w-4" />
            <h3 className="font-semibold">Debug output</h3>
          </div>
          <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap text-xs leading-5">
            {JSON.stringify(debugPayload, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function ResultsView({ result, fixes, pages, healthReport, healthScore }) {
  const competitorInsights = safeArray(result?.competitor_insights);
  const warnings = safeArray(result?.crawl_warnings);
  const provider = result?.ai_provider || "";

  return (
    <div className="space-y-6">
      <HealthSummary
        healthReport={healthReport}
        healthScore={healthScore}
        pages={pages}
        fixes={fixes}
        provider={provider}
      />

      {warnings.length > 0 ? (
        <div className="rounded-3xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
          <div className="mb-2 flex items-center gap-2 font-semibold">
            <AlertCircle className="h-4 w-4" />
            Scan notes
          </div>
          <ul className="space-y-1">
            {warnings.map((warning, index) => (
              <li key={index}>• {warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {competitorInsights.length > 0 ? (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-purple-700" />
            <h3 className="text-lg font-semibold text-slate-950">
              Competitor opportunities
            </h3>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {competitorInsights.map((insight, index) => (
              <div
                key={index}
                className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
              >
                <h4 className="font-semibold text-slate-950">
                  {insight.headline || insight.title || "Competitor insight"}
                </h4>
                {insight.evidence ? (
                  <p className="mt-2 text-sm text-slate-600">
                    {insight.evidence}
                  </p>
                ) : null}
                {insight.what_to_add || insight.recommended_action ? (
                  <p className="mt-3 text-sm font-medium text-slate-800">
                    What to add:{" "}
                    {insight.what_to_add || insight.recommended_action}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <Wrench className="h-5 w-5 text-blue-700" />
          <h3 className="text-lg font-semibold text-slate-950">
            Recommended fixes
          </h3>
        </div>

        {fixes.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600">
            No fixes were returned from this scan.
          </div>
        ) : (
          <div className="space-y-4">
            {fixes.map((fix, index) => (
              <FindingCard key={fix.id || fix.fix_id || index} fix={fix} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function HealthSummary({ healthReport, healthScore, pages, fixes, provider }) {
  const score =
    numberOrNull(healthReport?.health_score) ?? numberOrNull(healthScore);

  const grade =
    healthReport?.health_grade ||
    healthReport?.status_label ||
    scoreToLabel(score);

  const summary =
    healthReport?.overall_explanation ||
    healthReport?.plain_english_summary ||
    "The scan completed. Review the recommendations below.";

  const whatIsWorking = safeArray(healthReport?.what_is_working);
  const topConcerns = safeArray(healthReport?.top_concerns);
  const quickWins = safeArray(healthReport?.quick_wins);
  const biggerProjects = safeArray(healthReport?.bigger_projects);

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <HeartPulse className="h-5 w-5 text-emerald-700" />
            <h3 className="text-lg font-semibold text-slate-950">
              Website health
            </h3>
          </div>

          <p className="mt-3 max-w-3xl text-base leading-7 text-slate-700">
            {summary}
          </p>

          {provider ? (
            <p className="mt-2 text-xs text-slate-500">
              AI review provider: {provider}
            </p>
          ) : null}
        </div>

        <div className="rounded-3xl bg-slate-950 px-6 py-5 text-white">
          <div className="text-sm text-slate-300">Health score</div>
          <div className="mt-1 text-4xl font-bold">
            {score === null ? "—" : `${score}`}
            {score !== null ? <span className="text-xl">/100</span> : null}
          </div>
          <div className="mt-1 text-sm text-slate-300">{grade}</div>
        </div>
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <MetricCard label="Pages scanned" value={pages.length} />
        <MetricCard label="Recommendations" value={fixes.length} />
        <MetricCard
          label="High priority"
          value={
            fixes.filter((fix) =>
              ["critical", "high"].includes(String(fix.priority))
            ).length
          }
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {whatIsWorking.length > 0 ? (
          <HealthList
            title="What is working"
            icon={<CheckCircle2 className="h-4 w-4 text-emerald-700" />}
            items={whatIsWorking}
          />
        ) : null}

        {quickWins.length > 0 ? (
          <HealthCards
            title="Quick wins"
            icon={<Sparkles className="h-4 w-4 text-purple-700" />}
            items={quickWins}
          />
        ) : null}

        {topConcerns.length > 0 ? (
          <HealthCards
            title="Top concerns"
            icon={<AlertCircle className="h-4 w-4 text-amber-700" />}
            items={topConcerns}
          />
        ) : null}

        {biggerProjects.length > 0 ? (
          <HealthCards
            title="For your web person"
            icon={<Wrench className="h-4 w-4 text-blue-700" />}
            items={biggerProjects}
          />
        ) : null}
      </div>

      {healthReport?.next_best_step ? (
        <div className="mt-5 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
          <strong>Next best step:</strong> {healthReport.next_best_step}
        </div>
      ) : null}
    </section>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function HealthList({ title, icon, items }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex items-center gap-2 font-semibold text-slate-950">
        {icon}
        {title}
      </div>
      <ul className="space-y-2 text-sm text-slate-700">
        {items.slice(0, 5).map((item, index) => (
          <li key={index}>• {String(item)}</li>
        ))}
      </ul>
    </div>
  );
}

function HealthCards({ title, icon, items }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex items-center gap-2 font-semibold text-slate-950">
        {icon}
        {title}
      </div>

      <div className="space-y-3">
        {items.slice(0, 4).map((item, index) => (
          <div key={index} className="rounded-xl bg-white p-3">
            <div className="font-medium text-slate-950">
              {item.title || item.headline || item.action || String(item)}
            </div>

            {item.plain_english_explanation ||
            item.explanation ||
            item.action ? (
              <p className="mt-1 text-sm text-slate-600">
                {item.plain_english_explanation ||
                  item.explanation ||
                  item.action}
              </p>
            ) : null}

            {item.why_it_matters || item.why || item.expected_benefit ? (
              <p className="mt-1 text-xs text-slate-500">
                {item.why_it_matters || item.why || item.expected_benefit}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function FindingCard({ fix }) {
  const priority = String(fix.priority || "medium");
  const category = fix.customer_category || friendlyCategory(fix.category);
  const affectedPages = buildFriendlyAffectedPages(fix);
  const steps = safeArray(
    fix.what_to_do || fix.what_to_do_steps || fix.fix_steps
  );

  const isBrokenPage =
    String(fix.category || "").includes("404") ||
    String(fix.category || "").includes("broken") ||
    String(fix.customer_category || "").toLowerCase().includes("broken");

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap gap-2">
        <Badge>{priority}</Badge>
        <Badge>{category}</Badge>
      </div>

      <h4 className="mt-4 text-xl font-semibold text-slate-950">
        {fix.issue_title || fix.title || "Website recommendation"}
      </h4>

      <p className="mt-2 text-base leading-7 text-slate-600">
        {fix.plain_english_explanation ||
          fix.plain_english_summary ||
          "This was found during the website scan."}
      </p>

      {isBrokenPage ? (
        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <strong>Plain-English note:</strong> These pages may be old links,
          hidden pages, unavailable pages, or pages that blocked the scanner.
          Review the examples before assuming visitors are seeing a problem.
        </div>
      ) : null}

      {fix.why_it_matters ? (
        <div className="mt-4">
          <div className="text-sm font-semibold text-slate-950">
            Why this matters
          </div>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            {fix.why_it_matters}
          </p>
        </div>
      ) : null}

      {steps.length > 0 ? (
        <div className="mt-4">
          <div className="text-sm font-semibold text-slate-950">
            What to do next
          </div>
          <ol className="mt-2 space-y-1 text-sm leading-6 text-slate-600">
            {steps.slice(0, 5).map((step, index) => (
              <li key={index}>
                {index + 1}. {step}
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {affectedPages.length > 0 ? (
        <div className="mt-5">
          <div className="text-sm font-semibold text-slate-950">
            Example affected pages
          </div>

          <div className="mt-2 grid gap-2">
            {affectedPages.slice(0, 6).map((page, index) => (
              <div
                key={`${page.path}-${index}`}
                className="rounded-2xl border border-slate-200 bg-slate-50 p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-900">
                    {page.label}
                  </span>

                  {page.statusCode ? (
                    <span className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-600">
                      Status {page.statusCode}
                    </span>
                  ) : null}
                </div>

                <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                  <ExternalLink className="h-3 w-3" />
                  <code>{page.path}</code>
                </div>
              </div>
            ))}
          </div>

          {affectedPages.length > 6 ? (
            <p className="mt-2 text-xs text-slate-500">
              Plus {affectedPages.length - 6} more affected page
              {affectedPages.length - 6 === 1 ? "" : "s"}.
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function Badge({ children }) {
  return (
    <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700">
      {children}
    </span>
  );
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
/* Dashboard persistence                                                       */
/* -------------------------------------------------------------------------- */

function saveScanForDashboard({
  result,
  scannerPayload,
  normalizedScanner,
  normalizedReview,
}) {
  try {
    if (typeof window === "undefined" || !window.localStorage) return;

    const now = new Date().toISOString();

    const record = {
      id: `scan_${Date.now()}`,
      created_at: now,
      website_url:
        result?.normalized_url ||
        result?.website_url ||
        scannerPayload?.website_url ||
        "",
      domain: result?.domain || normalizedScanner?.domain || "",
      scan_mode:
        result?.scan_mode ||
        normalizedScanner?.scan_mode ||
        scannerPayload?.scan_mode ||
        "",
      ai_provider:
        result?.ai_provider ||
        normalizedReview?.ai_provider ||
        "scanner_fallback",
      result: {
        ...result,
        created_at: now,
        website_url:
          result?.website_url ||
          scannerPayload?.website_url ||
          result?.normalized_url ||
          "",
        normalized_url:
          result?.normalized_url ||
          normalizedScanner?.normalized_url ||
          scannerPayload?.website_url ||
          "",
      },
    };

    window.localStorage.setItem(
      DASHBOARD_LAST_SCAN_KEY,
      JSON.stringify(record)
    );

    window.localStorage.setItem(
      "SEO_AUTOPILOT_LAST_SCAN",
      JSON.stringify(record)
    );

    const existingHistory =
      safeJsonParseForDashboard(
        window.localStorage.getItem(DASHBOARD_HISTORY_KEY)
      ) || [];

    const cleanedHistory = Array.isArray(existingHistory)
      ? existingHistory.filter(
          (item) => item?.website_url !== record.website_url
        )
      : [];

    const nextHistory = [record, ...cleanedHistory].slice(0, 5);

    window.localStorage.setItem(
      DASHBOARD_HISTORY_KEY,
      JSON.stringify(nextHistory)
    );

    window.localStorage.setItem(
      "SEO_AUTOPILOT_SCAN_HISTORY",
      JSON.stringify(nextHistory)
    );

    window.dispatchEvent(new Event("seo-autopilot-scan-saved"));
  } catch (error) {
    console.warn("Could not save scan result for dashboard", error);
  }
}

function safeJsonParseForDashboard(value) {
  try {
    if (!value) return null;
    return JSON.parse(value);
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Friendly affected pages                                                     */
/* -------------------------------------------------------------------------- */

function buildFriendlyAffectedPages(fix) {
  const examples = safeArray(fix?.details?.examples);
  const affectedPages = safeArray(fix?.affected_pages);

  if (examples.length > 0) {
    return examples
      .map((example) => {
        const rawUrl = example.url || example.page_url || example.path || "";
        const path = cleanPath(rawUrl);

        if (!path) return null;

        return {
          path,
          label:
            cleanString(example.readable_label) ||
            cleanString(example.title) ||
            friendlyPageLabel(path) ||
            "Affected page",
          statusCode: example.status_code || example.status || "",
        };
      })
      .filter(Boolean);
  }

  return affectedPages
    .map((page) => {
      const path = cleanPath(page);

      if (!path) return null;

      return {
        path,
        label: friendlyPageLabel(path),
        statusCode: "",
      };
    })
    .filter(Boolean);
}

function friendlyPageLabel(pathOrUrl) {
  const path = cleanPath(pathOrUrl);
  const language = getLanguageNameFromPath(path);

  const cleaned = path
    .replace(/^\/(en|fr|es|de|it|pt|nl)(\/|$)/i, "/")
    .replace(/^\/+/, "")
    .replace(/\/+$/, "");

  if (!cleaned) {
    return language ? `${language} homepage` : "Homepage";
  }

  const parts = cleaned.split("/").filter(Boolean);

  if (parts[0] === "category" && parts[1]) {
    const category = humanizeSlug(parts.slice(1).join(" / "));

    return language
      ? `${language} category page: ${category}`
      : `Category page: ${category}`;
  }

  if (parts[0] === "listing" && parts[1]) {
    const listing = humanizeSlug(parts.slice(1).join(" / "));

    return language
      ? `${language} listing page: ${listing}`
      : `Listing page: ${listing}`;
  }

  if (parts[0] === "annonce" && parts[1]) {
    const page = humanizeSlug(parts[1]);

    return language
      ? `${language} activity page: ${page}`
      : `Activity page: ${page}`;
  }

  if (parts[0] === "wine" && parts[1]) {
    return `Wine page: ${humanizeSlug(parts.slice(1).join(" / "))}`;
  }

  const label = humanizeSlug(parts.join(" / "));

  return language ? `${language} page: ${label}` : label;
}

function getLanguageNameFromPath(pathOrUrl) {
  const path = cleanPath(pathOrUrl);
  const match = path.match(/^\/(en|fr|es|de|it|pt|nl)(\/|$)/i);

  if (!match) return "";

  const map = {
    en: "English",
    fr: "French",
    es: "Spanish",
    de: "German",
    it: "Italian",
    pt: "Portuguese",
    nl: "Dutch",
  };

  return map[match[1].toLowerCase()] || "";
}

function humanizeSlug(value) {
  return String(value || "")
    .replace(/-/g, " ")
    .replace(/_/g, " ")
    .replace(/\s*\/\s*/g, " / ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function cleanPath(input) {
  try {
    const parsed = new URL(String(input || ""), "https://example.com");
    const path = parsed.pathname || "/";

    return path !== "/" && path.endsWith("/") ? path.slice(0, -1) : path;
  } catch {
    const value = String(input || "/").split("?")[0].split("#")[0];

    if (!value || value === "/") return "/";

    return value.endsWith("/") && value !== "/" ? value.slice(0, -1) : value;
  }
}

/* -------------------------------------------------------------------------- */
/* Small helpers                                                               */
/* -------------------------------------------------------------------------- */

function pickFirstNonEmptyArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }

  return [];
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;

  const number = Number(value);

  return Number.isFinite(number) ? number : null;
}

function cleanString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function friendlyCategory(category) {
  const map = {
    meta_title: "Search appearance",
    meta_description: "Search appearance",
    canonical: "Technical SEO",
    schema: "Technical SEO",
    thin_content: "Page content",
    duplicate_content: "Search appearance",
    "404_error": "Broken pages",
    broken_page: "Broken pages",
    redirect: "Page redirects",
    internal_link: "Technical SEO",
    performance: "Website performance",
    web_dev: "Website setup",
    robots_txt: "Search visibility",
    js_rendering: "Website setup",
    indexability: "Technical SEO",
    mobile_setup: "Technical SEO",
    social_metadata: "Technical SEO",
    performance_hint: "Technical SEO",
    competitor_gap: "Competitor opportunities",
  };

  return map[category] || "Website improvement";
}

function scoreToLabel(score) {
  if (score === null || score === undefined) return "Scan complete";
  if (score >= 85) return "Great shape";
  if (score >= 70) return "Good start";
  if (score >= 45) return "Needs attention";
  return "Needs urgent attention";
}