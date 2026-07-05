import React, { useEffect, useMemo, useState } from "react";

/**
 * AdvancedScanner.jsx
 *
 * Drop this into your Advanced Scanner page.
 *
 * IMPORTANT:
 * - Change API_ENDPOINT below if your Base44/Deno function route is different.
 * - Expected response shape is flexible. This page supports:
 *   - scan_summary
 *   - recommended_actions
 *   - competitor_insights
 *   - findings
 *   - pages
 *   - technical_details
 *
 * If your backend currently returns different keys, normalize them inside
 * normalizeScanResult().
 */

const API_ENDPOINT = "/api/functions/advanced_scanner";

const SCAN_STEPS = [
  {
    key: "access",
    label: "Checking site access",
    text: "Checking whether your website can be scanned.",
  },
  {
    key: "important_pages",
    label: "Finding important pages",
    text: "Finding your homepage, service pages, contact page, and other priority URLs first.",
  },
  {
    key: "competitors",
    label: "Discovering competitors",
    text: "Looking for businesses ranking for similar searches.",
  },
  {
    key: "crawl",
    label: "Scanning your website",
    text: "Checking titles, headings, content depth, trust signals, technical basics, and crawlability.",
  },
  {
    key: "comparison",
    label: "Comparing competitor pages",
    text: "Comparing your site against competitor pages that Google is already showing.",
  },
  {
    key: "ai_review",
    label: "Creating recommendations",
    text: "Turning the findings into plain-English actions.",
  },
];

const DEPTH_OPTIONS = {
  quick: {
    label: "Quick scan",
    description: "Up to 25 pages",
    maxPages: 25,
  },
  standard: {
    label: "Standard scan",
    description: "Up to 75 pages",
    maxPages: 75,
  },
  deep: {
    label: "Deep scan",
    description: "Larger resumable crawl",
    maxPages: 200,
  },
};

const DEFAULT_RESULT = {
  scan_summary: null,
  recommended_actions: [],
  competitor_insights: [],
  findings: [],
  pages: [],
  technical_details: null,
  raw: null,
};

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function cleanUrl(url) {
  return String(url || "").trim();
}

function ensureProtocol(url) {
  const trimmed = cleanUrl(url);
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function getDomain(url) {
  try {
    return new URL(ensureProtocol(url)).hostname.replace(/^www\./, "");
  } catch {
    return url || "";
  }
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString() : "0";
}

function scoreLabel(score) {
  const number = Number(score || 0);
  if (number >= 80) return "Strong";
  if (number >= 60) return "Good start";
  if (number >= 40) return "Needs work";
  return "Needs urgent attention";
}

function scoreColor(score) {
  const number = Number(score || 0);
  if (number >= 80) return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (number >= 60) return "bg-blue-100 text-blue-800 border-blue-200";
  if (number >= 40) return "bg-amber-100 text-amber-800 border-amber-200";
  return "bg-red-100 text-red-800 border-red-200";
}

function priorityClass(priority) {
  const value = String(priority || "").toLowerCase();

  if (value.includes("high") || value.includes("critical")) {
    return "bg-red-100 text-red-800 border-red-200";
  }

  if (value.includes("medium")) {
    return "bg-amber-100 text-amber-800 border-amber-200";
  }

  if (value.includes("low")) {
    return "bg-slate-100 text-slate-700 border-slate-200";
  }

  return "bg-blue-100 text-blue-800 border-blue-200";
}

function categoryClass(category) {
  const value = String(category || "").toLowerCase();

  if (value.includes("competitor")) return "bg-purple-100 text-purple-800 border-purple-200";
  if (value.includes("content")) return "bg-blue-100 text-blue-800 border-blue-200";
  if (value.includes("technical")) return "bg-slate-100 text-slate-800 border-slate-200";
  if (value.includes("local")) return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (value.includes("trust")) return "bg-indigo-100 text-indigo-800 border-indigo-200";
  if (value.includes("performance")) return "bg-orange-100 text-orange-800 border-orange-200";

  return "bg-slate-100 text-slate-700 border-slate-200";
}

function gapTypeLabel(type) {
  const value = String(type || "").replace(/_/g, " ");

  if (!value) return "Competitor gap";

  return value.charAt(0).toUpperCase() + value.slice(1);
}

function normalizeScanResult(raw) {
  if (!raw) return DEFAULT_RESULT;

  const data = raw.data || raw.result || raw;

  const pages =
    safeArray(data.pages) ||
    safeArray(data.scanned_pages) ||
    safeArray(data.crawl_pages);

  const findings =
    safeArray(data.findings) ||
    safeArray(data.fixes) ||
    safeArray(data.issues) ||
    [];

  const competitorInsights =
    safeArray(data.competitor_insights) ||
    safeArray(data.competitorInsights) ||
    safeArray(data.competitor_gaps) ||
    safeArray(data.competitor_recommendations) ||
    [];

  const recommendedActions =
    safeArray(data.recommended_actions) ||
    safeArray(data.recommendedActions) ||
    safeArray(data.top_recommended_actions) ||
    findings
      .filter((item) => String(item.priority || "").toLowerCase().includes("high"))
      .slice(0, 5)
      .map((item) => ({
        fix_id: item.id || item.fix_id,
        title: item.title,
        plain_english_summary:
          item.plain_english_summary ||
          item.summary ||
          item.description ||
          "This issue may be affecting how clearly customers and search engines understand your site.",
        why_it_matters:
          item.why_it_matters ||
          "Fixing this can make the page clearer, easier to trust, and more useful for visitors.",
        what_to_do_steps: item.fix_steps || item.steps || item.what_to_do_steps || [],
        who_can_do_this: item.who_can_do_this || "Business owner or web designer",
        time_estimate: item.time_estimate || "30 minutes",
        priority: item.priority || "High",
        affected_pages: item.affected_pages || item.pages || [],
      }));

  const summary =
    data.scan_summary ||
    data.summary ||
    {
      score: data.score || data.overall_score || calculateFallbackScore(findings),
      status_label: data.status_label,
      plain_english_summary:
        data.plain_english_summary ||
        data.ai_summary ||
        "The scan completed. Review the recommended actions below to see what to improve first.",
      pages_scanned:
        data.pages_scanned ||
        data.page_count ||
        pages.filter((page) => String(page.status || "").toLowerCase() !== "failed").length,
      pages_failed:
        data.pages_failed ||
        pages.filter((page) => String(page.status || "").toLowerCase() === "failed").length,
      high_priority_count:
        data.high_priority_count ||
        findings.filter((item) =>
          String(item.priority || "").toLowerCase().includes("high")
        ).length,
      competitor_gap_count:
        data.competitor_gap_count ||
        competitorInsights.length,
    };

  return {
    scan_summary: summary,
    recommended_actions: recommendedActions,
    competitor_insights: competitorInsights,
    findings,
    pages,
    technical_details:
      data.technical_details ||
      data.technicalDetails ||
      data.crawl_details ||
      data.debug ||
      null,
    raw,
  };
}

function calculateFallbackScore(findings) {
  const high = findings.filter((item) =>
    String(item.priority || "").toLowerCase().includes("high")
  ).length;

  const medium = findings.filter((item) =>
    String(item.priority || "").toLowerCase().includes("medium")
  ).length;

  const low = findings.filter((item) =>
    String(item.priority || "").toLowerCase().includes("low")
  ).length;

  const penalty = high * 12 + medium * 6 + low * 2;
  return Math.max(0, Math.min(100, 100 - penalty));
}

async function runAdvancedScan(payload) {
  const response = await fetch(API_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw new Error(errorText || `Scan failed with status ${response.status}`);
  }

  return response.json();
}

function Badge({ children, className = "" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
        className
      )}
    >
      {children}
    </span>
  );
}

function Card({ children, className = "" }) {
  return (
    <div className={cx("rounded-2xl border border-slate-200 bg-white shadow-sm", className)}>
      {children}
    </div>
  );
}

function SectionHeader({ eyebrow, title, description, right }) {
  return (
    <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        {eyebrow ? (
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-700">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="text-2xl font-bold tracking-tight text-slate-950">{title}</h2>
        {description ? (
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
        ) : null}
      </div>
      {right ? <div>{right}</div> : null}
    </div>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <h3 className="text-base font-semibold text-slate-950">{title}</h3>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
    </div>
  );
}

function Toggle({ checked, onChange, label, help }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex w-full items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/40"
    >
      <div>
        <p className="text-sm font-semibold text-slate-950">{label}</p>
        {help ? <p className="mt-1 text-xs leading-5 text-slate-600">{help}</p> : null}
      </div>
      <span
        className={cx(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition",
          checked ? "bg-blue-600" : "bg-slate-300"
        )}
      >
        <span
          className={cx(
            "absolute top-1 h-4 w-4 rounded-full bg-white transition",
            checked ? "left-6" : "left-1"
          )}
        />
      </span>
    </button>
  );
}

function ProgressTimeline({ currentStep, progress }) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-slate-200 bg-slate-50 p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-950">Running advanced scan</h3>
            <p className="mt-1 text-sm text-slate-600">
              We are prioritising important pages first, then competitor comparison.
            </p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold text-blue-700">{Math.round(progress)}%</p>
            <p className="text-xs text-slate-500">Progress</p>
          </div>
        </div>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full rounded-full bg-blue-600 transition-all duration-500"
            style={{ width: `${Math.max(5, Math.min(100, progress))}%` }}
          />
        </div>
      </div>

      <div className="p-5">
        <div className="space-y-4">
          {SCAN_STEPS.map((step, index) => {
            const isDone = index < currentStep;
            const isActive = index === currentStep;

            return (
              <div key={step.key} className="flex gap-4">
                <div
                  className={cx(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-bold",
                    isDone
                      ? "border-emerald-600 bg-emerald-600 text-white"
                      : isActive
                        ? "border-blue-600 bg-blue-600 text-white"
                        : "border-slate-300 bg-white text-slate-500"
                  )}
                >
                  {isDone ? "✓" : index + 1}
                </div>
                <div className="min-w-0">
                  <p
                    className={cx(
                      "text-sm font-semibold",
                      isActive ? "text-blue-800" : "text-slate-950"
                    )}
                  >
                    {step.label}
                  </p>
                  <p className="mt-0.5 text-sm leading-5 text-slate-600">{step.text}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

function SummaryCards({ summary }) {
  const score = Number(summary?.score || 0);

  const cards = [
    {
      label: "Overall SEO health",
      value: score,
      suffix: "/100",
      badge: summary?.status_label || scoreLabel(score),
      badgeClass: scoreColor(score),
      helper: summary?.plain_english_summary || "Review the top actions below.",
    },
    {
      label: "Top fixes",
      value: summary?.high_priority_count || 0,
      suffix: "",
      badge: "Start here",
      badgeClass: "bg-red-100 text-red-800 border-red-200",
      helper: "High-priority recommendations to review first.",
    },
    {
      label: "Competitor gaps",
      value: summary?.competitor_gap_count || 0,
      suffix: "",
      badge: "What they do better",
      badgeClass: "bg-purple-100 text-purple-800 border-purple-200",
      helper: "Specific areas where competitors appear stronger.",
    },
    {
      label: "Pages scanned",
      value: summary?.pages_scanned || 0,
      suffix: "",
      badge:
        Number(summary?.pages_failed || 0) > 0
          ? `${summary?.pages_failed} failed/skipped`
          : "Scan complete",
      badgeClass:
        Number(summary?.pages_failed || 0) > 0
          ? "bg-amber-100 text-amber-800 border-amber-200"
          : "bg-emerald-100 text-emerald-800 border-emerald-200",
      helper: "Successful crawlable pages checked.",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.label} className="p-5">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-medium text-slate-600">{card.label}</p>
            <Badge className={card.badgeClass}>{card.badge}</Badge>
          </div>
          <div className="mt-4 flex items-end gap-1">
            <p className="text-4xl font-black tracking-tight text-slate-950">
              {formatNumber(card.value)}
            </p>
            {card.suffix ? (
              <p className="mb-1 text-sm font-semibold text-slate-500">{card.suffix}</p>
            ) : null}
          </div>
          <p className="mt-3 text-sm leading-5 text-slate-600">{card.helper}</p>
        </Card>
      ))}
    </div>
  );
}

function RecommendedActionCard({ action, index }) {
  const [open, setOpen] = useState(index === 0);
  const steps = safeArray(action.what_to_do_steps || action.fix_steps || action.steps);
  const affectedPages = safeArray(action.affected_pages || action.pages);

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-start justify-between gap-4 p-5 text-left"
      >
        <div className="flex gap-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
            {index + 1}
          </div>
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge className={priorityClass(action.priority || "High")}>
                {action.priority || "High priority"}
              </Badge>
              <Badge className="border-blue-200 bg-blue-50 text-blue-800">
                {action.time_estimate || "30 minutes"}
              </Badge>
              <Badge className="border-slate-200 bg-slate-50 text-slate-700">
                {action.who_can_do_this || "Business owner or web designer"}
              </Badge>
            </div>
            <h3 className="text-lg font-bold text-slate-950">
              {action.title || "Recommended action"}
            </h3>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
              {action.plain_english_summary ||
                action.summary ||
                "This recommendation can help make your website clearer and more useful."}
            </p>
          </div>
        </div>
        <span className="text-xl text-slate-400">{open ? "−" : "+"}</span>
      </button>

      {open ? (
        <div className="border-t border-slate-200 bg-slate-50 p-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <div>
              <h4 className="text-sm font-bold text-slate-950">Why it matters</h4>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {action.why_it_matters ||
                  "This helps visitors understand what you offer and helps search engines interpret the page more clearly."}
              </p>
            </div>

            <div>
              <h4 className="text-sm font-bold text-slate-950">What to do next</h4>
              {steps.length > 0 ? (
                <ol className="mt-2 space-y-2 text-sm leading-6 text-slate-600">
                  {steps.map((step, stepIndex) => (
                    <li key={`${step}-${stepIndex}`} className="flex gap-2">
                      <span className="font-bold text-blue-700">{stepIndex + 1}.</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Review the affected pages and improve the content, trust signals, or technical setup
                  described in this recommendation.
                </p>
              )}
            </div>
          </div>

          {affectedPages.length > 0 ? (
            <div className="mt-5">
              <h4 className="text-sm font-bold text-slate-950">Affected pages</h4>
              <div className="mt-2 flex flex-wrap gap-2">
                {affectedPages.slice(0, 8).map((page, pageIndex) => {
                  const url = typeof page === "string" ? page : page.url;

                  return (
                    <span
                      key={`${url}-${pageIndex}`}
                      className="max-w-full truncate rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700"
                    >
                      {url}
                    </span>
                  );
                })}
                {affectedPages.length > 8 ? (
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500">
                    +{affectedPages.length - 8} more
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

function CompetitorInsightCard({ insight }) {
  return (
    <Card className="overflow-hidden border-purple-200">
      <div className="border-b border-purple-100 bg-purple-50 p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap gap-2">
              <Badge className="border-purple-200 bg-white text-purple-800">
                {gapTypeLabel(insight.gap_type)}
              </Badge>
              {insight.serp_position ? (
                <Badge className="border-slate-200 bg-white text-slate-700">
                  Search position #{insight.serp_position}
                </Badge>
              ) : null}
            </div>
            <h3 className="text-lg font-bold text-slate-950">
              {insight.title || "Competitor advantage found"}
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {insight.what_they_do_better ||
                insight.summary ||
                "A competitor page appears to give users or search engines more useful information."}
            </p>
          </div>

          <div className="shrink-0 rounded-xl border border-purple-100 bg-white p-3 text-sm">
            <p className="font-semibold text-slate-950">
              {insight.competitor_domain || insight.domain || "Competitor"}
            </p>
            {insight.keyword ? (
              <p className="mt-1 text-xs text-slate-500">Keyword: {insight.keyword}</p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="grid gap-5 p-5 lg:grid-cols-2">
        <div>
          <h4 className="text-sm font-bold text-slate-950">Evidence</h4>
          {Array.isArray(insight.evidence) ? (
            <ul className="mt-2 space-y-2 text-sm leading-6 text-slate-600">
              {insight.evidence.map((item, index) => (
                <li key={`${item}-${index}`} className="flex gap-2">
                  <span className="text-purple-700">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {insight.evidence ||
                "The competitor page appears to contain stronger signals than the matching page on your site."}
            </p>
          )}
        </div>

        <div>
          <h4 className="text-sm font-bold text-slate-950">Recommended action</h4>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {insight.recommended_action ||
              "Use this as inspiration to improve your own page. Do not copy competitor text; add your own useful, specific information."}
          </p>

          {insight.related_user_page ? (
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Related page on your site
              </p>
              <p className="mt-1 break-all text-sm text-slate-700">
                {insight.related_user_page}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

function DiagnosisPanel({ summary, recommendedActions, competitorInsights }) {
  const topAction = recommendedActions[0];
  const topCompetitorInsight = competitorInsights[0];

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-slate-200 bg-slate-50 p-5">
        <h3 className="text-lg font-bold text-slate-950">Plain-English website diagnosis</h3>
        <p className="mt-1 text-sm text-slate-600">
          The technical scan has been translated into business-friendly priorities.
        </p>
      </div>

      <div className="grid gap-0 divide-y divide-slate-200 lg:grid-cols-4 lg:divide-x lg:divide-y-0">
        <div className="p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
            The main issue
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {summary?.plain_english_summary ||
              "Your website can be improved by making key pages clearer, more helpful, and easier for search engines to understand."}
          </p>
        </div>

        <div className="p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
            Best next step
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {topAction?.title ||
              "Start with the highest-priority recommendation before smaller technical fixes."}
          </p>
        </div>

        <div className="p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
            Competitor signal
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {topCompetitorInsight?.what_they_do_better ||
              topCompetitorInsight?.title ||
              "Competitor comparison will appear here when enough competitor data is found."}
          </p>
        </div>

        <div className="p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
            Good things found
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {summary?.positive_findings ||
              "Use the page table below to see which pages already have titles, headings, and crawlable content."}
          </p>
        </div>
      </div>
    </Card>
  );
}

function FindingsTable({ findings }) {
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [openId, setOpenId] = useState(null);

  const categories = useMemo(() => {
    const unique = new Set(
      findings
        .map((item) => item.category || item.type)
        .filter(Boolean)
        .map(String)
    );

    return ["all", ...Array.from(unique)];
  }, [findings]);

  const filteredFindings = useMemo(() => {
    return findings.filter((item) => {
      const priority = String(item.priority || "").toLowerCase();
      const category = String(item.category || item.type || "").toLowerCase();

      const priorityMatch =
        priorityFilter === "all" || priority.includes(priorityFilter.toLowerCase());

      const categoryMatch =
        categoryFilter === "all" || category === categoryFilter.toLowerCase();

      return priorityMatch && categoryMatch;
    });
  }, [findings, priorityFilter, categoryFilter]);

  if (!findings.length) {
    return (
      <EmptyState
        title="No detailed findings returned"
        description="The scan did not return individual findings. If the backend completed successfully, check that it sends a findings, fixes, or issues array."
      />
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50 p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-950">
            {filteredFindings.length} of {findings.length} findings shown
          </p>
          <p className="text-xs text-slate-500">
            Technical details are collapsed by default for non-technical users.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <select
            value={priorityFilter}
            onChange={(event) => setPriorityFilter(event.target.value)}
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="all">All priorities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <select
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            {categories.map((category) => (
              <option key={category} value={category}>
                {category === "all" ? "All categories" : category}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="divide-y divide-slate-200">
        {filteredFindings.map((finding, index) => {
          const id = finding.id || finding.fix_id || `${finding.title}-${index}`;
          const isOpen = openId === id;
          const affectedPages = safeArray(finding.affected_pages || finding.pages);
          const steps = safeArray(finding.fix_steps || finding.steps || finding.what_to_do_steps);

          return (
            <div key={id}>
              <button
                type="button"
                onClick={() => setOpenId(isOpen ? null : id)}
                className="flex w-full items-start justify-between gap-4 p-5 text-left hover:bg-slate-50"
              >
                <div>
                  <div className="mb-2 flex flex-wrap gap-2">
                    <Badge className={priorityClass(finding.priority)}>
                      {finding.priority || "Priority"}
                    </Badge>
                    <Badge className={categoryClass(finding.category || finding.type)}>
                      {finding.category || finding.type || "SEO"}
                    </Badge>
                    {finding.who_can_do_this ? (
                      <Badge className="border-slate-200 bg-slate-50 text-slate-700">
                        {finding.who_can_do_this}
                      </Badge>
                    ) : null}
                    {finding.time_estimate ? (
                      <Badge className="border-slate-200 bg-slate-50 text-slate-700">
                        {finding.time_estimate}
                      </Badge>
                    ) : null}
                  </div>

                  <h3 className="text-base font-bold text-slate-950">
                    {finding.title || "SEO finding"}
                  </h3>
                  <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
                    {finding.plain_english_summary ||
                      finding.summary ||
                      finding.description ||
                      "This item may need review."}
                  </p>
                </div>

                <span className="text-xl text-slate-400">{isOpen ? "−" : "+"}</span>
              </button>

              {isOpen ? (
                <div className="border-t border-slate-200 bg-slate-50 p-5">
                  <div className="grid gap-5 lg:grid-cols-3">
                    <div>
                      <h4 className="text-sm font-bold text-slate-950">Fix steps</h4>
                      {steps.length ? (
                        <ol className="mt-2 space-y-2 text-sm leading-6 text-slate-600">
                          {steps.map((step, stepIndex) => (
                            <li key={`${step}-${stepIndex}`} className="flex gap-2">
                              <span className="font-bold text-blue-700">{stepIndex + 1}.</span>
                              <span>{step}</span>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          Review this issue and improve the affected page based on the explanation above.
                        </p>
                      )}
                    </div>

                    <div>
                      <h4 className="text-sm font-bold text-slate-950">Affected pages</h4>
                      {affectedPages.length ? (
                        <div className="mt-2 space-y-2">
                          {affectedPages.slice(0, 10).map((page, pageIndex) => {
                            const url = typeof page === "string" ? page : page.url;

                            return (
                              <p
                                key={`${url}-${pageIndex}`}
                                className="break-all rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700"
                              >
                                {url}
                              </p>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          No specific page was attached to this finding.
                        </p>
                      )}
                    </div>

                    <div>
                      <h4 className="text-sm font-bold text-slate-950">
                        Technical details
                      </h4>
                      <p className="mt-2 whitespace-pre-wrap rounded-xl border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-600">
                        {finding.technical_detail ||
                          finding.technical_details ||
                          finding.raw_detail ||
                          "No extra technical detail was returned for this finding."}
                      </p>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function PagesTable({ pages }) {
  const [showAll, setShowAll] = useState(false);
  const visiblePages = showAll ? pages : pages.slice(0, 20);

  if (!pages.length) {
    return (
      <EmptyState
        title="No pages returned"
        description="The scan did not return page-level data. Check that the backend sends a pages array."
      />
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-bold">Page URL</th>
              <th className="px-4 py-3 font-bold">Type</th>
              <th className="px-4 py-3 font-bold">Status</th>
              <th className="px-4 py-3 font-bold">Words</th>
              <th className="px-4 py-3 font-bold">Title</th>
              <th className="px-4 py-3 font-bold">Meta</th>
              <th className="px-4 py-3 font-bold">H1</th>
              <th className="px-4 py-3 font-bold">Issues</th>
              <th className="px-4 py-3 font-bold">Notes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {visiblePages.map((page, index) => {
              const status = String(page.status || "scanned").toLowerCase();
              const likelyClientRendered =
                page.likely_client_rendered ||
                page.client_rendered ||
                page.is_spa_shell;

              return (
                <tr key={`${page.url}-${index}`} className="align-top hover:bg-slate-50">
                  <td className="max-w-[260px] break-all px-4 py-3 text-xs text-slate-700">
                    {page.url}
                  </td>
                  <td className="px-4 py-3">
                    <Badge className="border-slate-200 bg-slate-50 text-slate-700">
                      {page.page_type || page.type || "Page"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      className={
                        status.includes("fail") || status.includes("error")
                          ? "border-red-200 bg-red-100 text-red-800"
                          : "border-emerald-200 bg-emerald-100 text-emerald-800"
                      }
                    >
                      {page.status || "Scanned"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {formatNumber(page.word_count || page.words)}
                  </td>
                  <td className="px-4 py-3">
                    {page.title ? (
                      <span className="text-emerald-700">Found</span>
                    ) : (
                      <span className="text-red-700">Missing</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {page.meta_description ? (
                      <span className="text-emerald-700">Found</span>
                    ) : (
                      <span className="text-red-700">Missing</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {page.h1 ? (
                      <span className="text-emerald-700">Found</span>
                    ) : (
                      <span className="text-red-700">Missing</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {formatNumber(page.issue_count || page.issues_found || 0)}
                  </td>
                  <td className="max-w-[260px] px-4 py-3 text-xs leading-5 text-slate-600">
                    {likelyClientRendered ? (
                      <span>
                        This page may load much of its content in the browser. Content warnings may
                        need manual review.
                      </span>
                    ) : (
                      page.notes || "—"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pages.length > 20 ? (
        <div className="border-t border-slate-200 bg-slate-50 p-4 text-center">
          <button
            type="button"
            onClick={() => setShowAll(!showAll)}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100"
          >
            {showAll ? "Show fewer pages" : `Show all ${pages.length} pages`}
          </button>
        </div>
      ) : null}
    </Card>
  );
}

function TechnicalDetails({ technicalDetails }) {
  const [open, setOpen] = useState(false);

  if (!technicalDetails) {
    return (
      <EmptyState
        title="No technical crawl details returned"
        description="Technical details will appear here when the backend sends crawl_details or technical_details."
      />
    );
  }

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-4 bg-slate-50 p-5 text-left"
      >
        <div>
          <h3 className="text-lg font-bold text-slate-950">Technical crawl details</h3>
          <p className="mt-1 text-sm text-slate-600">
            For technical users. Hidden by default so business owners are not overwhelmed.
          </p>
        </div>
        <span className="text-xl text-slate-400">{open ? "−" : "+"}</span>
      </button>

      {open ? (
        <div className="border-t border-slate-200 p-5">
          <pre className="max-h-[520px] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">
            {JSON.stringify(technicalDetails, null, 2)}
          </pre>
        </div>
      ) : null}
    </Card>
  );
}

export default function AdvancedScannerPage() {
  const [url, setUrl] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [location, setLocation] = useState("");
  const [targetKeywords, setTargetKeywords] = useState("");
  const [depth, setDepth] = useState("standard");
  const [maxPages, setMaxPages] = useState(DEPTH_OPTIONS.standard.maxPages);

  const [competitorDiscovery, setCompetitorDiscovery] = useState(true);
  const [aiReview, setAiReview] = useState(true);
  const [includeSitemap, setIncludeSitemap] = useState(true);
  const [respectRobots, setRespectRobots] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [isScanning, setIsScanning] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [result, setResult] = useState(DEFAULT_RESULT);

  useEffect(() => {
    setMaxPages(DEPTH_OPTIONS[depth].maxPages);
  }, [depth]);

  useEffect(() => {
    if (!isScanning) return undefined;

    const interval = window.setInterval(() => {
      setProgress((previous) => {
        const next = Math.min(previous + Math.random() * 7 + 2, 92);
        const stepIndex = Math.min(
          SCAN_STEPS.length - 1,
          Math.floor((next / 100) * SCAN_STEPS.length)
        );

        setCurrentStep(stepIndex);
        return next;
      });
    }, 1000);

    return () => window.clearInterval(interval);
  }, [isScanning]);

  const domainPreview = useMemo(() => getDomain(url), [url]);

  async function handleSubmit(event) {
    event.preventDefault();

    const websiteUrl = ensureProtocol(url);

    if (!websiteUrl) {
      setError("Enter a website URL before running the scan.");
      return;
    }

    setError("");
    setResult(DEFAULT_RESULT);
    setIsScanning(true);
    setCurrentStep(0);
    setProgress(4);

    const payload = {
      url: websiteUrl,
      website_url: websiteUrl,

      business_type: businessType.trim(),
      business_location: location.trim(),
      location: location.trim(),

      target_keywords: targetKeywords
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),

      scan_depth: depth,
      max_pages: Number(maxPages || DEPTH_OPTIONS[depth].maxPages),

      competitor_discovery: competitorDiscovery,
      include_competitors: competitorDiscovery,

      ai_review: aiReview,
      plain_english_ai_review: aiReview,

      include_sitemap: includeSitemap,
      respect_robots_txt: respectRobots,

      output_contract: {
        scan_summary: true,
        recommended_actions: true,
        competitor_insights: true,
        findings: true,
        pages: true,
        technical_details: true,
      },
    };

    try {
      const rawResult = await runAdvancedScan(payload);
      const normalized = normalizeScanResult(rawResult);

      setProgress(100);
      setCurrentStep(SCAN_STEPS.length - 1);
      setResult(normalized);
    } catch (scanError) {
      console.error(scanError);
      setError(
        scanError?.message ||
          "The advanced scan could not be completed. Check the function route and try again."
      );
    } finally {
      setIsScanning(false);
    }
  }

  const hasResult = Boolean(result.scan_summary);

  return (
    <main className="min-h-screen bg-slate-100">
      <section className="border-b border-slate-200 bg-gradient-to-br from-slate-950 via-blue-950 to-slate-900">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8 lg:py-16">
          <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
            <div>
              <Badge className="border-blue-300/40 bg-blue-400/10 text-blue-100">
                Advanced SEO diagnosis
              </Badge>

              <h1 className="mt-5 max-w-4xl text-4xl font-black tracking-tight text-white md:text-6xl">
                Advanced SEO Scanner
              </h1>

              <p className="mt-5 max-w-2xl text-lg leading-8 text-blue-100">
                Scan your website, compare it with real competitors, and get plain-English fixes
                you can actually act on.
              </p>

              <div className="mt-8 grid gap-3 text-sm text-blue-100 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="font-bold text-white">Plain-English fixes</p>
                  <p className="mt-1 text-blue-100/80">
                    Technical findings turned into simple next steps.
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="font-bold text-white">Competitor gaps</p>
                  <p className="mt-1 text-blue-100/80">
                    Shows what better-ranking pages are doing differently.
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="font-bold text-white">Important pages first</p>
                  <p className="mt-1 text-blue-100/80">
                    Prioritises service, about, contact, and high-value pages.
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="font-bold text-white">Technical detail available</p>
                  <p className="mt-1 text-blue-100/80">
                    Crawl data is still there, but hidden until needed.
                  </p>
                </div>
              </div>
            </div>

            <Card className="border-white/10 bg-white p-5 shadow-2xl">
              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label className="text-sm font-bold text-slate-950">Website URL</label>
                  <input
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    placeholder="example.com"
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-base outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                  />
                  {domainPreview ? (
                    <p className="mt-2 text-xs text-slate-500">
                      Scanner target: <span className="font-semibold">{domainPreview}</span>
                    </p>
                  ) : null}
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="text-sm font-bold text-slate-950">
                      Business type
                    </label>
                    <input
                      value={businessType}
                      onChange={(event) => setBusinessType(event.target.value)}
                      placeholder="Plumber, accountant, dentist..."
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-bold text-slate-950">
                      Location / country
                    </label>
                    <input
                      value={location}
                      onChange={(event) => setLocation(event.target.value)}
                      placeholder="Bristol, UK"
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-sm font-bold text-slate-950">
                    Scan depth
                  </label>
                  <div className="mt-2 grid gap-3 sm:grid-cols-3">
                    {Object.entries(DEPTH_OPTIONS).map(([key, option]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setDepth(key)}
                        className={cx(
                          "rounded-xl border p-4 text-left transition",
                          depth === key
                            ? "border-blue-600 bg-blue-50 ring-4 ring-blue-100"
                            : "border-slate-200 bg-white hover:border-blue-300"
                        )}
                      >
                        <p className="text-sm font-bold text-slate-950">{option.label}</p>
                        <p className="mt-1 text-xs text-slate-500">{option.description}</p>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid gap-3">
                  <Toggle
                    checked={competitorDiscovery}
                    onChange={setCompetitorDiscovery}
                    label="Competitor discovery"
                    help="Finds businesses ranking for similar keywords so we can compare what they are doing better."
                  />

                  <Toggle
                    checked={aiReview}
                    onChange={setAiReview}
                    label="Plain-English AI review"
                    help="Turns technical findings into simple explanations, steps, and effort estimates."
                  />
                </div>

                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-sm font-semibold text-blue-700 hover:text-blue-900"
                >
                  {showAdvanced ? "Hide advanced settings" : "Show advanced settings"}
                </button>

                {showAdvanced ? (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label className="text-sm font-bold text-slate-950">
                          Max pages
                        </label>
                        <input
                          type="number"
                          min="1"
                          max="500"
                          value={maxPages}
                          onChange={(event) => setMaxPages(event.target.value)}
                          className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                        />
                      </div>

                      <div>
                        <label className="text-sm font-bold text-slate-950">
                          Target keywords
                        </label>
                        <input
                          value={targetKeywords}
                          onChange={(event) => setTargetKeywords(event.target.value)}
                          placeholder="keyword one, keyword two"
                          className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                        />
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <Toggle
                        checked={includeSitemap}
                        onChange={setIncludeSitemap}
                        label="Include sitemap URLs"
                        help="Uses sitemap URLs to find important pages faster."
                      />

                      <Toggle
                        checked={respectRobots}
                        onChange={setRespectRobots}
                        label="Respect robots.txt"
                        help="Avoids scanning URLs that the website asks crawlers not to access."
                      />
                    </div>
                  </div>
                ) : null}

                {error ? (
                  <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-800">
                    {error}
                  </div>
                ) : null}

                <button
                  type="submit"
                  disabled={isScanning}
                  className={cx(
                    "w-full rounded-xl px-5 py-4 text-base font-bold text-white transition",
                    isScanning
                      ? "cursor-not-allowed bg-slate-400"
                      : "bg-blue-600 hover:bg-blue-700"
                  )}
                >
                  {isScanning ? "Running advanced scan..." : "Run Advanced Scan"}
                </button>

                <p className="text-center text-xs leading-5 text-slate-500">
                  We check your pages, competitor examples, SEO basics, content depth, trust
                  signals, and technical issues.
                </p>
              </form>
            </Card>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl space-y-10 px-4 py-10 sm:px-6 lg:px-8">
        {isScanning ? (
          <ProgressTimeline currentStep={currentStep} progress={progress} />
        ) : null}

        {!isScanning && !hasResult ? (
          <Card className="p-8">
            <div className="mx-auto max-w-3xl text-center">
              <h2 className="text-2xl font-bold tracking-tight text-slate-950">
                Ready to scan your website
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Enter a URL above to get an action-first SEO report. The results will prioritise
                plain-English fixes, competitor gaps, and the most important pages before raw crawl
                details.
              </p>
            </div>
          </Card>
        ) : null}

        {!isScanning && hasResult ? (
          <>
            <SummaryCards summary={result.scan_summary} />

            <DiagnosisPanel
              summary={result.scan_summary}
              recommendedActions={result.recommended_actions}
              competitorInsights={result.competitor_insights}
            />

            <section>
              <SectionHeader
                eyebrow="Start here"
                title="What to fix first"
                description="These are the highest-value actions. They are written for business owners first, with technical details kept underneath."
              />

              {result.recommended_actions.length ? (
                <div className="space-y-4">
                  {result.recommended_actions.slice(0, 5).map((action, index) => (
                    <RecommendedActionCard
                      key={action.fix_id || action.id || `${action.title}-${index}`}
                      action={action}
                      index={index}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No recommended actions returned"
                  description="The scan completed, but no top actions were returned. Check that the backend sends recommended_actions or top_recommended_actions."
                />
              )}
            </section>

            <section>
              <SectionHeader
                eyebrow="Competitor comparison"
                title="What competitors are doing better"
                description="This section should surface specific gaps, such as FAQs, stronger service copy, schema, trust signals, reviews, calls to action, and location detail."
              />

              {result.competitor_insights.length ? (
                <div className="grid gap-4 lg:grid-cols-2">
                  {result.competitor_insights.map((insight, index) => (
                    <CompetitorInsightCard
                      key={`${insight.title}-${insight.competitor_domain}-${index}`}
                      insight={insight}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="Competitor comparison was limited"
                  description="We could not find enough relevant competitor data for this scan. Add target keywords manually and run the scan again."
                />
              )}
            </section>

            <section>
              <SectionHeader
                eyebrow="Full audit"
                title="All findings"
                description="Filter by priority or category. Each finding leads with a simple explanation, with technical detail hidden underneath."
              />
              <FindingsTable findings={result.findings} />
            </section>

            <section>
              <SectionHeader
                eyebrow="Crawl view"
                title="Pages scanned"
                description="Review what the scanner found on each page, including missing titles, headings, descriptions, thin content, and client-rendered warnings."
              />
              <PagesTable pages={result.pages} />
            </section>

            <section>
              <SectionHeader
                eyebrow="For technical users"
                title="Technical crawl details"
                description="Robots.txt, sitemap, redirects, skipped URLs, failed pages, timeouts, and raw crawl diagnostics."
              />
              <TechnicalDetails technicalDetails={result.technical_details} />
            </section>
          </>
        ) : null}
      </section>
    </main>
  );
}