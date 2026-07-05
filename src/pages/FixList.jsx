import React, { useEffect, useMemo, useState } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clipboard,
  HelpCircle,
  Loader2,
  Search,
  Sparkles,
  Wrench,
} from "lucide-react";

const ACTIVE_STATUSES = new Set([
  "auto_fixed",
  "needs_approval",
  "needs_developer",
  "open",
  "in_progress",
]);

const FILTERS = [
  { key: "all", label: "All" },
  { key: "priority", label: "Priority" },
  { key: "auto_fixed", label: "Prepared" },
  { key: "needs_approval", label: "Needs review" },
  { key: "needs_developer", label: "May need help" },
];

function getIssueBucket(issue) {
  if (issue.status === "needs_developer" || issue.requires_developer) {
    return "needs_developer";
  }

  if (issue.status === "needs_approval" || issue.requires_approval) {
    return "needs_approval";
  }

  if (issue.status === "auto_fixed" || issue.can_auto_fix) {
    return "auto_fixed";
  }

  return "needs_approval";
}

function getBucketLabel(bucket) {
  if (bucket === "auto_fixed") return "Prepared";
  if (bucket === "needs_approval") return "Needs review";
  if (bucket === "needs_developer") return "May need help";
  return "Recommended";
}

function getBucketDescription(bucket) {
  if (bucket === "auto_fixed") return "Ready-to-review recommendations.";
  if (bucket === "needs_approval") return "Items that need a decision.";
  if (bucket === "needs_developer") return "Larger improvements for help or cleanup.";
  return "Website recommendations.";
}

function getBucketIcon(bucket) {
  if (bucket === "auto_fixed") return CheckCircle2;
  if (bucket === "needs_approval") return HelpCircle;
  if (bucket === "needs_developer") return Wrench;
  return Sparkles;
}

function friendlyCategory(category, customerCategory) {
  if (customerCategory) return customerCategory;

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
    image_alt_text: "Images",
  };

  return map[category] || "Website improvement";
}

function getPriorityLabel(priority) {
  if (priority === "critical" || priority === "high") return "High";
  if (priority === "medium") return "Medium";
  return "Low";
}

function getPriorityRank(priority) {
  if (priority === "critical") return 0;
  if (priority === "high") return 1;
  if (priority === "medium") return 2;
  return 3;
}

function cleanUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.hash = "";
    parsed.search = "";

    const path = parsed.pathname || "/";

    if (path !== "/" && path.endsWith("/")) {
      return path.slice(0, -1);
    }

    return path;
  } catch {
    const value = String(url || "/").split("?")[0].split("#")[0];

    if (!value || value === "/") return "/";

    return value.endsWith("/") && value !== "/" ? value.slice(0, -1) : value;
  }
}

function formatPageLabel(url) {
  const path = cleanUrl(url);

  if (!path || path === "/") return "Homepage";

  return path
    .split("/")
    .filter(Boolean)
    .map((part) =>
      decodeURIComponent(part)
        .replace(/[-_]/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase())
    )
    .join(" › ");
}

function getAffectedPages(issue) {
  const pages = [];

  if (Array.isArray(issue.affected_pages)) {
    pages.push(...issue.affected_pages);
  }

  if (issue.page_url) {
    pages.push(issue.page_url);
  }

  return Array.from(new Set(pages.filter(Boolean).map(cleanUrl)));
}

function groupIssuesForDisplay(issues) {
  const active = issues.filter((issue) => ACTIVE_STATUSES.has(issue.status));
  const map = new Map();

  for (const issue of active) {
    const bucket = getIssueBucket(issue);
    const category = issue.category || "web_dev";
    const title = issue.issue_title || "Review this recommendation";
    const affectedPages = getAffectedPages(issue);
    const hasManyAffected = affectedPages.length > 1;

    const key = hasManyAffected
      ? [bucket, category, title].join("|").toLowerCase()
      : [bucket, category, title, cleanUrl(issue.page_url)].join("|").toLowerCase();

    if (!map.has(key)) {
      map.set(key, {
        ...issue,
        bucket,
        display_page_url: cleanUrl(issue.page_url || affectedPages[0] || "/"),
        affected_pages: affectedPages,
        grouped_count: 1,
        grouped_issue_ids: [issue.id],
      });
    } else {
      const existing = map.get(key);

      existing.grouped_count += 1;
      existing.grouped_issue_ids.push(issue.id);

      const pages = new Set([
        ...(existing.affected_pages || []),
        ...affectedPages,
        issue.page_url,
      ]);

      existing.affected_pages = Array.from(pages).filter(Boolean).map(cleanUrl);
    }
  }

  return Array.from(map.values()).sort((a, b) => {
    const priorityDiff = getPriorityRank(a.priority) - getPriorityRank(b.priority);
    if (priorityDiff !== 0) return priorityDiff;

    const bucketOrder = {
      needs_approval: 0,
      auto_fixed: 1,
      needs_developer: 2,
      open: 3,
    };

    const bucketDiff =
      (bucketOrder[a.bucket] ?? 9) - (bucketOrder[b.bucket] ?? 9);

    if (bucketDiff !== 0) return bucketDiff;

    return String(a.issue_title || "").localeCompare(String(b.issue_title || ""));
  });
}

function summarizeCounts(groupedIssues) {
  return {
    total: groupedIssues.length,
    auto_fixed: groupedIssues.filter((item) => item.bucket === "auto_fixed").length,
    needs_approval: groupedIssues.filter((item) => item.bucket === "needs_approval").length,
    needs_developer: groupedIssues.filter((item) => item.bucket === "needs_developer").length,
    high_priority: groupedIssues.filter(
      (item) => item.priority === "critical" || item.priority === "high"
    ).length,
  };
}

function formatScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number) || number <= 0) return "—";

  return `${Math.round(number)}`;
}

function getScoreLabel(value) {
  const number = Number(value);

  if (!Number.isFinite(number) || number <= 0) return "Score unavailable";
  if (number >= 85) return "Strong";
  if (number >= 70) return "Good";
  if (number >= 55) return "Needs cleanup";
  return "Needs attention";
}

function isStaleJob(job) {
  const staleStatuses = new Set([
    "queued",
    "crawling_html",
    "checking_metadata",
    "checking_canonicals",
    "checking_links",
    "finding_competitors",
    "benchmarking_competitors",
    "generating_recommendations",
    "in_progress",
  ]);

  if (!staleStatuses.has(job.status)) return false;

  const dateValue = job.started_at || job.created_date || job.created_at;

  if (!dateValue) return false;

  const ageMs = Date.now() - new Date(dateValue).getTime();

  return ageMs > 10 * 60 * 1000;
}

function formatJobStatus(job) {
  if (isStaleJob(job)) return "Could not complete";
  if (job.status === "complete") return "Complete";
  if (job.status === "failed") return "Could not complete";
  return "In progress";
}

function formatDate(value) {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "—";
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || "");
  } catch {
    console.warn("Could not copy text.");
  }
}

function StatCard({ label, value, helper, icon: Icon }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            {label}
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            {value}
          </p>
          {helper && <p className="mt-1 text-sm text-slate-500">{helper}</p>}
        </div>

        {Icon && (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100">
            <Icon className="h-4 w-4 text-slate-600" />
          </div>
        )}
      </div>
    </div>
  );
}

function RecommendationRow({ issue, onOpen }) {
  const Icon = getBucketIcon(issue.bucket);
  const affectedPages = Array.isArray(issue.affected_pages)
    ? issue.affected_pages
    : [];

  return (
    <button
      type="button"
      onClick={() => onOpen(issue)}
      className="group w-full border-b border-slate-100 px-5 py-4 text-left last:border-b-0 hover:bg-slate-50"
    >
      <div className="flex items-start gap-4">
        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100">
          <Icon className="h-4 w-4 text-slate-700" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-950">
              {issue.issue_title || "Review this recommendation"}
            </h3>

            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
              {getBucketLabel(issue.bucket)}
            </span>

            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
              {getPriorityLabel(issue.priority)}
            </span>
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-500">
            <span>{friendlyCategory(issue.category, issue.customer_category)}</span>
            <span>·</span>
            <span>
              {affectedPages.length > 1
                ? `${affectedPages.length} affected pages`
                : formatPageLabel(issue.page_url)}
            </span>
          </div>

          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            {issue.plain_english_explanation ||
              "This recommendation was prepared from your website scan."}
          </p>
        </div>

        <ChevronRight className="mt-2 h-4 w-4 shrink-0 text-slate-300 group-hover:text-slate-500" />
      </div>
    </button>
  );
}

function IssueModal({ issue, onClose }) {
  if (!issue) return null;

  const affectedPages = Array.isArray(issue.affected_pages)
    ? issue.affected_pages.filter(Boolean)
    : [];

  const recommendation =
    issue.ai_recommendation ||
    issue.recommended_value ||
    "Review this recommendation.";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/30 px-4 py-6 sm:items-center">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-blue-600">
              {getBucketLabel(issue.bucket)}
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
              {issue.issue_title}
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              {friendlyCategory(issue.category, issue.customer_category)} ·{" "}
              {formatPageLabel(issue.page_url)}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-50"
          >
            Close
          </button>
        </div>

        <div className="mt-6 space-y-5">
          <section>
            <h3 className="text-sm font-semibold text-slate-950">
              What we found
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {issue.plain_english_explanation ||
                "This recommendation was found during the scan."}
            </p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-950">
              Why it matters
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {issue.why_it_matters ||
                "Improving this can help visitors and search engines understand the website more clearly."}
            </p>
          </section>

          <section className="rounded-2xl bg-blue-50 p-4">
            <h3 className="text-sm font-semibold text-slate-950">
              Recommended next step
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-700">
              {recommendation}
            </p>
          </section>

          {affectedPages.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-slate-950">
                Affected pages
              </h3>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {affectedPages.slice(0, 12).map((page, index) => (
                  <div
                    key={`${page}-${index}`}
                    className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600"
                  >
                    {formatPageLabel(page)}
                  </div>
                ))}
              </div>
            </section>
          )}

          {issue.details && Object.keys(issue.details).length > 0 && (
            <details className="rounded-2xl bg-slate-50 p-4">
              <summary className="cursor-pointer text-sm font-medium text-slate-700">
                Technical details
              </summary>
              <pre className="mt-3 whitespace-pre-wrap break-words text-xs leading-5 text-slate-500">
                {JSON.stringify(issue.details, null, 2)}
              </pre>
            </details>
          )}
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            type="button"
            onClick={() => copyText(recommendation)}
            variant="outline"
            className="rounded-full border-slate-200 bg-white shadow-none"
          >
            <Clipboard className="mr-2 h-4 w-4" />
            Copy next step
          </Button>

          <Button
            asChild
            className="rounded-full bg-blue-600 px-5 text-white shadow-none hover:bg-blue-700"
          >
            <a href="/billing">Request help</a>
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function FixList() {
  const [loading, setLoading] = useState(true);
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [competitorInsights, setCompetitorInsights] = useState([]);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [activeFilter, setActiveFilter] = useState("all");
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    trackEvent("fix_list_viewed");

    const load = async () => {
      try {
        const user = await base44.auth.me();
        const activeProjectId = window.localStorage.getItem("active_project_id");

        let activeProject = null;

        if (activeProjectId) {
          try {
            activeProject =
              await base44.entities.BusinessProject.get(activeProjectId);
          } catch {}
        }

        if (!activeProject) {
          const projects = await base44.entities.BusinessProject.list(
            "-last_crawl_at",
            10
          );

          activeProject =
            projects.find(
              (item) =>
                item.owner_user_id === user.id || item.created_by_id === user.id
            ) ||
            projects[0] ||
            null;
        }

        setProject(activeProject);

        if (activeProject) {
          window.localStorage.setItem("active_project_id", activeProject.id);

          const [issueRows, jobRows, insights] = await Promise.all([
            base44.entities.SeoIssue.filter(
              { project_id: activeProject.id },
              "-created_date",
              300
            ),
            base44.entities.CrawlJob.filter(
              { project_id: activeProject.id },
              "-created_date",
              5
            ),
            base44.entities.CompetitorInsight.filter({
              project_id: activeProject.id,
            }).catch(() => []),
          ]);

          setIssues(issueRows || []);
          setJobs(jobRows || []);
          setCompetitorInsights(insights || []);
        }
      } catch (error) {
        console.warn("Could not load Fix List.", error);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const groupedIssues = useMemo(() => groupIssuesForDisplay(issues), [issues]);
  const counts = useMemo(() => summarizeCounts(groupedIssues), [groupedIssues]);

  const priorityIssues = groupedIssues.filter(
    (item) => item.priority === "critical" || item.priority === "high"
  );

  const visibleIssues = useMemo(() => {
    if (activeFilter === "all") return groupedIssues;
    if (activeFilter === "priority") return priorityIssues;
    return groupedIssues.filter((item) => item.bucket === activeFilter);
  }, [activeFilter, groupedIssues, priorityIssues]);

  const firstAction =
    priorityIssues[0] ||
    groupedIssues.find((item) => item.bucket === "needs_approval") ||
    groupedIssues[0] ||
    null;

  const latestJob = jobs[0] || null;

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-6 lg:py-10">
        <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div>
            <p className="text-sm font-medium text-blue-600">
              Website recommendations
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              Fix List
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-slate-500">
              A prioritized list of what to review, prepare, or ask for help
              with.
            </p>
          </div>

          <div className="flex gap-2">
            <Button
              asChild
              className="rounded-full bg-blue-600 px-5 text-white shadow-none hover:bg-blue-700"
            >
              <a href="/crawl-status">Scan Website</a>
            </Button>

            <Button
              asChild
              variant="outline"
              className="rounded-full border-slate-200 bg-white px-5 shadow-none"
            >
              <a href="/assistant">Ask AI</a>
            </Button>
          </div>
        </div>

        <div className="mb-6 grid gap-3 md:grid-cols-4">
          <StatCard
            label="Score"
            value={formatScore(project?.seo_score)}
            helper={getScoreLabel(project?.seo_score)}
            icon={Sparkles}
          />
          <StatCard
            label="Recommendations"
            value={counts.total}
            helper={`${counts.high_priority} high priority`}
            icon={AlertCircle}
          />
          <StatCard
            label="Pages scanned"
            value={latestJob?.pages_crawled ?? "—"}
            helper={latestJob ? formatDate(latestJob.completed_at || latestJob.started_at) : "No scan yet"}
            icon={Search}
          />
          <StatCard
            label="May need help"
            value={counts.needs_developer}
            helper="Website setup or cleanup"
            icon={Wrench}
          />
        </div>

        {firstAction && (
          <div className="mb-6 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-sm font-medium text-blue-600">
                  Recommended first step
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-950">
                  {firstAction.issue_title}
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                  {firstAction.ai_recommendation ||
                    firstAction.recommended_value ||
                    firstAction.plain_english_explanation}
                </p>
              </div>

              <Button
                type="button"
                onClick={() => setSelectedIssue(firstAction)}
                className="w-fit rounded-full bg-slate-950 px-5 text-white shadow-none hover:bg-slate-800"
              >
                View details
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        <div className="mb-4 flex flex-wrap gap-2">
          {FILTERS.map((filter) => {
            const isActive = activeFilter === filter.key;

            return (
              <button
                key={filter.key}
                type="button"
                onClick={() => setActiveFilter(filter.key)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-slate-950 text-white"
                    : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {filter.label}
              </button>
            );
          })}
        </div>

        {competitorInsights.length > 0 && (
          <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-slate-950">
                  Competitor opportunities found
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  Review where competitor pages may be stronger.
                </p>
              </div>

              <Button
                asChild
                variant="outline"
                className="rounded-full border-slate-200 bg-white shadow-none"
              >
                <a href="/competitors">View</a>
              </Button>
            </div>
          </div>
        )}

        {groupedIssues.length === 0 ? (
          <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <h2 className="text-xl font-semibold tracking-tight text-slate-950">
              No recommendations yet.
            </h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              Run a website scan first. Once the scan finishes, your Fix List
              will appear here.
            </p>

            <Button
              asChild
              className="mt-5 rounded-full bg-blue-600 px-5 text-white shadow-none hover:bg-blue-700"
            >
              <a href="/crawl-status">Scan Website</a>
            </Button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-slate-950">
                  {activeFilter === "all"
                    ? "All recommendations"
                    : FILTERS.find((item) => item.key === activeFilter)?.label}
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {visibleIssues.length} item{visibleIssues.length === 1 ? "" : "s"}
                </p>
              </div>
            </div>

            {visibleIssues.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-sm text-slate-500">
                  No recommendations in this section.
                </p>
              </div>
            ) : (
              visibleIssues.map((issue) => (
                <RecommendationRow
                  key={issue.id || issue.grouped_issue_ids?.join("-")}
                  issue={issue}
                  onOpen={setSelectedIssue}
                />
              ))
            )}
          </div>
        )}

        {jobs.length > 0 && (
          <section className="mt-6 rounded-3xl border border-slate-200 bg-white shadow-sm">
            <button
              type="button"
              onClick={() => setShowHistory((value) => !value)}
              className="flex w-full items-center justify-between px-5 py-4 text-left"
            >
              <div>
                <h2 className="text-base font-semibold text-slate-950">
                  Scan history
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Last {jobs.length} scans
                </p>
              </div>

              <ChevronDown
                className={`h-4 w-4 text-slate-400 transition ${
                  showHistory ? "rotate-180" : ""
                }`}
              />
            </button>

            {showHistory && (
              <div className="overflow-x-auto border-t border-slate-100">
                <table className="w-full min-w-[680px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
                      <th className="px-5 py-3 font-medium">Date</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                      <th className="px-5 py-3 font-medium">Pages</th>
                      <th className="px-5 py-3 font-medium">Recommendations</th>
                      <th className="px-5 py-3 font-medium">Score</th>
                    </tr>
                  </thead>

                  <tbody>
                    {jobs.map((job) => (
                      <tr
                        key={job.id}
                        className="border-b border-slate-100 text-slate-600 last:border-b-0"
                      >
                        <td className="px-5 py-4">
                          {formatDate(job.completed_at || job.started_at)}
                        </td>
                        <td className="px-5 py-4">{formatJobStatus(job)}</td>
                        <td className="px-5 py-4">
                          {typeof job.pages_crawled === "number"
                            ? `${job.pages_crawled} pages`
                            : "—"}
                        </td>
                        <td className="px-5 py-4">
                          {typeof job.issues_found === "number"
                            ? `${job.issues_found} recommendations`
                            : "—"}
                        </td>
                        <td className="px-5 py-4">
                          {formatScore(job.seo_score || project?.seo_score)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        <IssueModal
          issue={selectedIssue}
          onClose={() => setSelectedIssue(null)}
        />
      </div>
    </div>
  );
}