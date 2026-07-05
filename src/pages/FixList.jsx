import React, { useEffect, useMemo, useState } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Clipboard,
  HelpCircle,
  Loader2,
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
  if (bucket === "auto_fixed") return "Recommendations prepared for review.";
  if (bucket === "needs_approval") return "Items that need your decision.";
  if (bucket === "needs_developer") {
    return "Larger improvements for a website editor or done-for-you help.";
  }

  return "Recommended website improvements.";
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
  if (priority === "critical" || priority === "high") return "High impact";
  if (priority === "medium") return "Medium impact";
  return "Lower impact";
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
    const bucketOrder = {
      needs_approval: 0,
      auto_fixed: 1,
      needs_developer: 2,
      open: 3,
    };

    const priorityOrder = {
      critical: 0,
      high: 1,
      medium: 2,
      low: 3,
    };

    const bucketDiff =
      (bucketOrder[a.bucket] ?? 9) - (bucketOrder[b.bucket] ?? 9);

    if (bucketDiff !== 0) return bucketDiff;

    return (
      (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9)
    );
  });
}

function summarizeCounts(groupedIssues) {
  return {
    auto_fixed: groupedIssues.filter((item) => item.bucket === "auto_fixed")
      .length,
    needs_approval: groupedIssues.filter(
      (item) => item.bucket === "needs_approval"
    ).length,
    needs_developer: groupedIssues.filter(
      (item) => item.bucket === "needs_developer"
    ).length,
  };
}

function formatScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number) || number <= 0) return "Score unavailable";

  return `${Math.round(number)}`;
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

function RecommendationCard({ issue, onOpen }) {
  const bucket = issue.bucket;
  const Icon = getBucketIcon(bucket);

  const affectedPages = Array.isArray(issue.affected_pages)
    ? issue.affected_pages
    : [];

  return (
    <button
      type="button"
      onClick={() => onOpen(issue)}
      className="w-full rounded-3xl border border-slate-200/80 bg-white p-5 text-left shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100">
            <Icon className="h-4 w-4 text-slate-700" />
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-slate-950">
                {issue.issue_title || "Review this recommendation"}
              </p>

              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                {friendlyCategory(issue.category, issue.customer_category)}
              </span>

              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                {getPriorityLabel(issue.priority)}
              </span>
            </div>

            <p className="mt-1 text-sm text-slate-500">
              {formatPageLabel(issue.page_url)}
              {affectedPages.length > 1 &&
                ` · ${affectedPages.length} affected pages`}
            </p>

            <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-600">
              {issue.plain_english_explanation ||
                "This recommendation was prepared from your website scan."}
            </p>
          </div>
        </div>

        <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-400" />
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

          <section>
            <h3 className="text-sm font-semibold text-slate-950">
              Recommended next step
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {recommendation}
            </p>
          </section>

          {affectedPages.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-slate-950">
                Affected pages
              </h3>
              <div className="mt-2 space-y-2">
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
            Copy recommendation
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
              200
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

  const prepared = groupedIssues.filter((item) => item.bucket === "auto_fixed");
  const needsReview = groupedIssues.filter(
    (item) => item.bucket === "needs_approval"
  );
  const mayNeedHelp = groupedIssues.filter(
    (item) => item.bucket === "needs_developer"
  );

  const firstAction = needsReview[0] || prepared[0] || mayNeedHelp[0] || null;

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div>
            <p className="text-sm font-medium text-blue-600">
              Website recommendations
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              Fix List
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-slate-500">
              SEO Autopilot scans your website, reviews important pages, looks
              for competitor opportunities when possible, and prepares a simple
              Fix List.
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

        {firstAction && (
          <button
            type="button"
            onClick={() => setSelectedIssue(firstAction)}
            className="mb-6 w-full rounded-3xl border border-slate-200/80 bg-white p-6 text-left shadow-sm transition hover:bg-slate-50"
          >
            <div className="flex items-start justify-between gap-5">
              <div>
                <p className="text-sm font-medium text-blue-600">
                  What to do first
                </p>
                <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                  {firstAction.issue_title}
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {firstAction.plain_english_explanation}
                </p>
              </div>

              <ArrowRight className="h-5 w-5 shrink-0 text-slate-400" />
            </div>
          </button>
        )}

        <div className="mb-6 grid gap-3 sm:grid-cols-3">
          {[
            ["auto_fixed", counts.auto_fixed],
            ["needs_approval", counts.needs_approval],
            ["needs_developer", counts.needs_developer],
          ].map(([bucket, count]) => {
            const Icon = getBucketIcon(bucket);

            return (
              <div
                key={bucket}
                className="rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-slate-950">
                      {getBucketLabel(bucket)}
                    </p>
                    <p className="mt-1 text-sm leading-5 text-slate-500">
                      {getBucketDescription(bucket)}
                    </p>
                  </div>

                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100">
                    <Icon className="h-4 w-4 text-slate-700" />
                  </div>
                </div>

                <p className="mt-4 text-3xl font-semibold tracking-tight text-slate-950">
                  {count}
                </p>
              </div>
            );
          })}
        </div>

        {competitorInsights.length > 0 && (
          <div className="mb-6 rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-slate-950">
                  Competitor opportunities
                </p>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  We found a few ways other pages may be stronger.
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
          <div className="rounded-3xl border border-slate-200/80 bg-white p-8 text-center shadow-sm">
            <h2 className="text-xl font-semibold tracking-tight text-slate-950">
              No recommendations yet.
            </h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              Run a website scan first. Once the scan finishes, your
              recommendations will appear here.
            </p>

            <Button
              asChild
              className="mt-5 rounded-full bg-blue-600 px-5 text-white shadow-none hover:bg-blue-700"
            >
              <a href="/crawl-status">Scan Website</a>
            </Button>
          </div>
        ) : (
          <div className="space-y-8">
            {prepared.length > 0 && (
              <section>
                <div className="mb-3 flex items-end justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-950">
                      Prepared
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Recommendations prepared for review.
                    </p>
                  </div>
                  <span className="text-sm text-slate-400">
                    {prepared.length}
                  </span>
                </div>

                <div className="space-y-3">
                  {prepared.map((issue) => (
                    <RecommendationCard
                      key={issue.id || issue.grouped_issue_ids?.join("-")}
                      issue={issue}
                      onOpen={setSelectedIssue}
                    />
                  ))}
                </div>
              </section>
            )}

            {needsReview.length > 0 && (
              <section>
                <div className="mb-3 flex items-end justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-950">
                      Needs review
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Items that need your decision.
                    </p>
                  </div>
                  <span className="text-sm text-slate-400">
                    {needsReview.length}
                  </span>
                </div>

                <div className="space-y-3">
                  {needsReview.map((issue) => (
                    <RecommendationCard
                      key={issue.id || issue.grouped_issue_ids?.join("-")}
                      issue={issue}
                      onOpen={setSelectedIssue}
                    />
                  ))}
                </div>
              </section>
            )}

            {mayNeedHelp.length > 0 && (
              <section>
                <div className="mb-3 flex items-end justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-950">
                      May need help
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Larger improvements for a website editor or done-for-you
                      help.
                    </p>
                  </div>
                  <span className="text-sm text-slate-400">
                    {mayNeedHelp.length}
                  </span>
                </div>

                <div className="space-y-3">
                  {mayNeedHelp.map((issue) => (
                    <RecommendationCard
                      key={issue.id || issue.grouped_issue_ids?.join("-")}
                      issue={issue}
                      onOpen={setSelectedIssue}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {jobs.length > 0 && (
          <section className="mt-10">
            <div className="mb-3">
              <h2 className="text-lg font-semibold text-slate-950">
                Scan history
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Your last 5 scans.
              </p>
            </div>

            <div className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
              <div className="grid grid-cols-5 gap-3 border-b border-slate-100 px-5 py-3 text-xs font-medium uppercase tracking-wide text-slate-400">
                <div>Date</div>
                <div>Status</div>
                <div>Pages</div>
                <div>Recommendations</div>
                <div>Score</div>
              </div>

              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="grid grid-cols-5 gap-3 border-b border-slate-100 px-5 py-4 text-sm text-slate-600 last:border-b-0"
                >
                  <div>{formatDate(job.completed_at || job.started_at)}</div>
                  <div>{formatJobStatus(job)}</div>
                  <div>
                    {typeof job.pages_crawled === "number"
                      ? `${job.pages_crawled} pages`
                      : "—"}
                  </div>
                  <div>
                    {typeof job.issues_found === "number"
                      ? `${job.issues_found} recommendations`
                      : "—"}
                  </div>
                  <div>{formatScore(job.seo_score || project?.seo_score)}</div>
                </div>
              ))}
            </div>
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