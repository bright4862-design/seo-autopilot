import React, { useEffect, useMemo, useState } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
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

function getBucketIcon(bucket) {
  if (bucket === "auto_fixed") return CheckCircle2;
  if (bucket === "needs_developer") return Wrench;
  return HelpCircle;
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
    return path !== "/" && path.endsWith("/") ? path.slice(0, -1) : path;
  } catch {
    return url || "/";
  }
}

function formatPageLabel(url) {
  const clean = cleanUrl(url);

  if (!clean || clean === "/") return "Homepage";

  return String(clean)
    .split("/")
    .filter(Boolean)
    .map((part) =>
      decodeURIComponent(part)
        .replace(/[-_]/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase())
    )
    .join(" › ");
}

function friendlyCategory(category, fallback) {
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
    web_dev: "Website setup",
    performance: "Speed and mobile",
    image_alt_text: "Images",
  };

  return fallback || map[category] || "Website improvement";
}

function groupIssues(issues) {
  const map = new Map();

  for (const issue of issues) {
    const bucket = getIssueBucket(issue);
    const key = [
      bucket,
      issue.category || "",
      issue.issue_title || "",
      issue.customer_category || "",
    ]
      .join("|")
      .toLowerCase();

    const affectedPages = Array.isArray(issue.affected_pages)
      ? issue.affected_pages
      : [];

    if (!map.has(key)) {
      map.set(key, {
        ...issue,
        bucket,
        affected_pages: Array.from(
          new Set([...(affectedPages || []), issue.page_url].filter(Boolean))
        ),
        grouped_count: 1,
      });
    } else {
      const existing = map.get(key);
      const pages = [
        ...(existing.affected_pages || []),
        ...(affectedPages || []),
        issue.page_url,
      ].filter(Boolean);

      existing.affected_pages = Array.from(new Set(pages));
      existing.grouped_count += 1;
    }
  }

  return Array.from(map.values());
}

export default function FixList() {
  const [loading, setLoading] = useState(true);
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [crawlJobs, setCrawlJobs] = useState([]);
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

        if (!activeProject) {
          setLoading(false);
          return;
        }

        setProject(activeProject);
        window.localStorage.setItem("active_project_id", activeProject.id);

        const [issueRows, jobs, insights] = await Promise.all([
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
          base44.entities.CompetitorInsight.filter(
            { project_id: activeProject.id },
            "-created_date",
            10
          ).catch(() => []),
        ]);

        const activeIssues = (issueRows || []).filter((item) =>
          ACTIVE_STATUSES.has(item.status)
        );

        setIssues(activeIssues);
        setCrawlJobs(jobs || []);
        setCompetitorInsights(insights || []);
      } catch (err) {
        console.warn("Could not load Fix List.", err);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const groupedIssues = useMemo(() => groupIssues(issues), [issues]);

  const prepared = groupedIssues.filter(
    (issue) => issue.bucket === "auto_fixed"
  );
  const needsReview = groupedIssues.filter(
    (issue) => issue.bucket === "needs_approval"
  );
  const mayNeedHelp = groupedIssues.filter(
    (issue) => issue.bucket === "needs_developer"
  );

  const firstPriority =
    needsReview[0] || prepared[0] || mayNeedHelp[0] || null;

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-[#F7F8FA]">
        <div className="mx-auto max-w-4xl px-6 py-12">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950">
            Fix List
          </h1>
          <p className="mt-3 text-slate-500">
            Start by scanning a website.
          </p>
          <Button asChild className="mt-6 rounded-full bg-blue-600">
            <a href="/crawl-status">Scan Website</a>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-medium text-blue-600">
              Website recommendations
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              Fix List
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-slate-500">
              SEO Autopilot scanned your website, reviewed the findings, and
              prepared the most useful next steps.
            </p>
          </div>

          <div className="flex gap-2">
            <Button
              asChild
              className="rounded-full bg-blue-600 px-5 text-white shadow-none hover:bg-blue-700"
            >
              <a href="/crawl-status">Scan Website</a>
            </Button>
          </div>
        </div>

        {firstPriority && (
          <div className="mb-6 rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-50">
                <Sparkles className="h-5 w-5 text-blue-600" />
              </div>

              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-blue-600">
                  What to do first
                </p>
                <h2 className="mt-1 text-lg font-semibold text-slate-950">
                  {firstPriority.issue_title}
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {firstPriority.plain_english_explanation}
                </p>
              </div>

              <button
                onClick={() => setSelectedIssue(firstPriority)}
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Review
              </button>
            </div>
          </div>
        )}

        <div className="mb-6 grid gap-3 md:grid-cols-3">
          <CounterCard label="Prepared" value={prepared.length} />
          <CounterCard label="Needs review" value={needsReview.length} />
          <CounterCard label="May need help" value={mayNeedHelp.length} />
        </div>

        {competitorInsights.length > 0 && (
          <div className="mb-6 rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-slate-950">
                  Competitor opportunities
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  We found a few ways other pages may be stronger.
                </p>
              </div>

              <Button asChild variant="outline" className="rounded-full">
                <a href="/competitors">View</a>
              </Button>
            </div>
          </div>
        )}

        {groupedIssues.length === 0 ? (
          <div className="rounded-3xl border border-slate-200/80 bg-white p-8 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">
              No major recommendations found.
            </h2>
            <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">
              No major recommendations were found based on the website content
              we could access. Run a deep scan for a more complete review.
            </p>
            <Button asChild className="mt-6 rounded-full bg-blue-600">
              <a href="/crawl-status">Scan Website</a>
            </Button>
          </div>
        ) : (
          <div className="space-y-6">
            <IssueSection
              title="Prepared"
              description="Recommendations prepared for review."
              issues={prepared}
              onSelect={setSelectedIssue}
            />

            <IssueSection
              title="Needs review"
              description="Items that need your decision."
              issues={needsReview}
              onSelect={setSelectedIssue}
            />

            <IssueSection
              title="May need help"
              description="Larger improvements for a website editor or done-for-you help."
              issues={mayNeedHelp}
              onSelect={setSelectedIssue}
            />
          </div>
        )}

        {crawlJobs.length > 0 && (
          <div className="mt-8 rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">
              Scan history
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Your last 5 scans.
            </p>

            <div className="mt-5 space-y-3">
              {crawlJobs.map((job) => (
                <div
                  key={job.id}
                  className="grid gap-2 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600 md:grid-cols-5"
                >
                  <div>{formatDate(job.created_date || job.started_at)}</div>
                  <div>{formatStatus(job.status)}</div>
                  <div>{job.pages_crawled ?? "—"} pages</div>
                  <div>{job.issues_found ?? "—"} recommendations</div>
                  <div>
                    {typeof job.seo_score === "number" && job.seo_score > 0
                      ? `Score ${job.seo_score}`
                      : "Score unavailable"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {selectedIssue && (
          <IssueModal
            issue={selectedIssue}
            onClose={() => setSelectedIssue(null)}
          />
        )}
      </div>
    </div>
  );
}

function CounterCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="text-2xl font-semibold text-slate-950">{value}</div>
      <div className="mt-1 text-sm text-slate-500">{label}</div>
    </div>
  );
}

function IssueSection({ title, description, issues, onSelect }) {
  if (!issues.length) return null;

  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <div className="mb-5">
        <h2 className="text-lg font-semibold text-slate-950">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
      </div>

      <div className="divide-y divide-slate-100">
        {issues.map((issue) => (
          <IssueRow key={issue.id} issue={issue} onSelect={onSelect} />
        ))}
      </div>
    </section>
  );
}

function IssueRow({ issue, onSelect }) {
  const bucket = getIssueBucket(issue);
  const Icon = getBucketIcon(bucket);
  const pages = Array.isArray(issue.affected_pages)
    ? issue.affected_pages
    : [];

  return (
    <button
      onClick={() => {
        trackEvent("recommendation_opened", {
          issue_id: issue.id,
          category: issue.category,
          status: issue.status,
        });
        onSelect(issue);
      }}
      className="flex w-full items-start gap-4 py-4 text-left hover:bg-slate-50/70"
    >
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100">
        <Icon className="h-4 w-4 text-slate-600" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-medium text-slate-950">{issue.issue_title}</h3>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">
            {getBucketLabel(bucket)}
          </span>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">
            {getPriorityLabel(issue.priority)}
          </span>
        </div>

        <p className="mt-1 text-sm leading-6 text-slate-600">
          {issue.plain_english_explanation}
        </p>

        <p className="mt-1 text-xs text-slate-400">
          {friendlyCategory(issue.category, issue.customer_category)} ·{" "}
          {pages.length > 1
            ? `${pages.length} affected pages`
            : formatPageLabel(issue.page_url)}
        </p>
      </div>

      <ChevronRight className="mt-2 h-4 w-4 shrink-0 text-slate-300" />
    </button>
  );
}

function IssueModal({ issue, onClose }) {
  const pages = Array.isArray(issue.affected_pages)
    ? issue.affected_pages
    : [];

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/30 px-4 pb-4 sm:items-center sm:pb-0">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-3xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-blue-600">
              {friendlyCategory(issue.category, issue.customer_category)}
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
              {issue.issue_title}
            </h2>
          </div>

          <button
            onClick={onClose}
            className="rounded-full bg-slate-100 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-200"
          >
            Close
          </button>
        </div>

        <div className="mt-6 space-y-5">
          <DetailBlock
            title="What we found"
            text={issue.plain_english_explanation}
          />
          <DetailBlock title="Why it matters" text={issue.why_it_matters} />
          <DetailBlock
            title="Recommended next step"
            text={issue.ai_recommendation || issue.recommended_value}
          />

          {pages.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-slate-950">
                Affected pages
              </h3>
              <div className="mt-2 space-y-2">
                {pages.slice(0, 20).map((page, index) => (
                  <div
                    key={`${page}-${index}`}
                    className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-600"
                  >
                    {formatPageLabel(page)}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-2xl bg-slate-50 p-4">
            <h3 className="text-sm font-medium text-slate-950">
              Technical details
            </h3>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              Category: {issue.category || "website improvement"}
              <br />
              Status: {getBucketLabel(getIssueBucket(issue))}
              <br />
              Priority: {getPriorityLabel(issue.priority)}
            </p>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button className="rounded-full bg-blue-600 text-white">
            Mark reviewed
          </Button>
          <Button variant="outline" className="rounded-full">
            Request help
          </Button>
        </div>
      </div>
    </div>
  );
}

function DetailBlock({ title, text }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-slate-950">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        {text || "No details available."}
      </p>
    </div>
  );
}

function formatDate(value) {
  if (!value) return "—";

  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(value));
  } catch {
    return "—";
  }
}

function formatStatus(status) {
  if (status === "complete") return "Complete";
  if (status === "failed") return "Could not complete";
  if (
    [
      "queued",
      "crawling_html",
      "checking_metadata",
      "checking_canonicals",
      "reading_sitemap",
      "checking_links",
      "finding_competitors",
      "benchmarking_competitors",
      "generating_recommendations",
      "in_progress",
    ].includes(status)
  ) {
    return "In progress";
  }

  return status || "—";
}