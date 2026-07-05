import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Globe, Calendar, ExternalLink } from "lucide-react";
import ScoreRing from "@/components/dashboard/ScoreRing";
import UrlSubmissionPanel from "@/components/dashboard/UrlSubmissionPanel";
import CrawlHistory from "@/components/dashboard/CrawlHistory";
import PullToRefresh from "@/components/layout/PullToRefresh";
import {
  ACTIVE_STATUSES,
  DONE_STATUSES,
  BUCKETS,
  countBuckets,
  getFirstStep,
  resolveActiveProject,
  getScoreBand,
  getScoreTrend,
} from "@/lib/appModel";
import { getTopCategory } from "@/lib/categoryLabels";

function plural(count, singular, pluralForm) {
  return count === 1 ? singular : pluralForm;
}

// Same visual as the Fix List's counter strip — each cell links to the
// Fix List, because the count IS the invitation to act.
function CounterRow({ counts }) {
  return (
    <div className="grid divide-y divide-slate-100 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
      {BUCKETS.map((bucket) => (
        <Link
          key={bucket.key}
          to="/issues"
          className="flex items-center justify-between px-5 py-4 transition-colors hover:bg-slate-50 sm:block sm:px-6"
        >
          <p className="text-sm text-slate-500">{bucket.title}</p>
          <p className="text-xl font-semibold text-slate-950 sm:mt-1">
            {counts[bucket.key]}
          </p>
        </Link>
      ))}
    </div>
  );
}

function QuickAction({ to, title, description }) {
  return (
    <Link
      to={to}
      className="group rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm transition-all hover:border-slate-300 hover:shadow-md sm:p-6"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-950">{title}</h3>
        <ExternalLink className="h-4 w-4 shrink-0 text-slate-300 transition-colors group-hover:text-blue-600" />
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
    </Link>
  );
}

function EmptyProjectState() {
  return (
    <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
      <h2 className="text-lg font-semibold text-slate-950">
        Welcome to SEO Autopilot
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600">
        Add your website and we&rsquo;ll prepare a simple Fix List — no SEO
        knowledge needed.
      </p>
      <Button
        asChild
        className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
      >
        <Link to="/onboarding">Set Up Your Website</Link>
      </Button>
    </div>
  );
}

export default function Dashboard() {
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]); // active issues only
  const [doneCount, setDoneCount] = useState(0);
  const [crawls, setCrawls] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const { user, project: activeProject } = await resolveActiveProject(base44);

      if (!activeProject) return;

      setProject(activeProject);

      const [issueData, jobs] = await Promise.all([
        base44.entities.SeoIssue.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
        base44.entities.CrawlJob.filter(
          { project_id: activeProject.id },
          "-started_at"
        ),
      ]);

      const all = issueData || [];
      setIssues(all.filter((issue) => ACTIVE_STATUSES.has(issue.status)));
      setDoneCount(
        all.filter((issue) => DONE_STATUSES.has(issue.status)).length
      );
      setCrawls(jobs || []);
    } catch (err) {
      console.warn("Could not load the dashboard.", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    trackEvent("dashboard_viewed");
    loadData();
  }, []);

  const counts = useMemo(() => countBuckets(issues), [issues]);
  const topOpportunity = useMemo(() => getTopCategory(issues), [issues]);
  const scoreTrend = useMemo(() => getScoreTrend(crawls), [crawls]);

  const handleCrawlDeleted = (id) => {
    setCrawls((prev) => prev.filter((c) => c.id !== id));
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-[#F7F8FA]">
        <div className="mx-auto w-full max-w-4xl px-5 py-16 sm:px-6">
          <EmptyProjectState />
        </div>
      </div>
    );
  }

  const scoreBand = getScoreBand(project.seo_score);

  // The big blue button is the NEXT ACTION, never "scan again" by default.
  // Priority mirrors getFirstStep(): approve → decide → delegate → scan.
  const primaryAction =
    counts.auto_fixed > 0
      ? {
          label: `Approve ${counts.auto_fixed} prepared ${plural(counts.auto_fixed, "fix", "fixes")}`,
          to: "/issues",
        }
      : counts.needs_approval > 0
        ? {
            label: `Review ${counts.needs_approval} ${plural(counts.needs_approval, "item", "items")}`,
            to: "/issues",
          }
        : counts.needs_developer > 0
          ? { label: "See bigger jobs", to: "/issues" }
          : { label: "Scan Website", to: "/crawl-status" };

  const showScanSecondary = primaryAction.to !== "/crawl-status";

  return (
    <PullToRefresh onRefresh={loadData}>
      <div className="min-h-screen bg-[#F7F8FA] dark:bg-slate-950">
        <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        {/* Header */}
        <div className="mb-8 flex flex-col items-start justify-between gap-5 sm:flex-row">
          <div>
            <p className="text-sm font-medium text-blue-600">Your website</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              {project.business_name}
            </h1>
            <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-500">
              <Globe className="h-3.5 w-3.5" />
              {project.website_url}
            </p>
          </div>

          <div className="flex items-center gap-3">
            {showScanSecondary && (
              <Button
                asChild
                variant="outline"
                className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50"
              >
                <Link to="/crawl-status">Scan Website</Link>
              </Button>
            )}

            <Button
              asChild
              className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
            >
              <Link to={primaryAction.to}>{primaryAction.label}</Link>
            </Button>
          </div>
        </div>

        {/* Score + what to do first */}
        <div className="mb-7 grid gap-6 lg:grid-cols-3">
          <div className="flex flex-col items-center justify-center rounded-3xl border border-slate-200/80 bg-white p-6 text-center shadow-sm">
            {typeof project.seo_score === "number" ? (
              <>
                <ScoreRing score={project.seo_score} />
                {scoreBand && (
                  <p className="mt-3 text-sm font-medium text-slate-950">
                    {scoreBand}
                  </p>
                )}
                {scoreTrend !== null && scoreTrend !== 0 && (
                  <p
                    className={`mt-1 text-xs font-medium ${
                      scoreTrend > 0 ? "text-emerald-600" : "text-slate-500"
                    }`}
                  >
                    {scoreTrend > 0 ? `+${scoreTrend}` : scoreTrend} since your
                    last scan
                  </p>
                )}
                {project.last_crawl_at && (
                  <p className="mt-2 flex items-center gap-1 text-xs text-slate-400">
                    <Calendar className="h-3 w-3" />
                    Last scan:{" "}
                    {new Date(project.last_crawl_at).toLocaleDateString()}
                  </p>
                )}
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-slate-950">
                  No score yet
                </p>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  Scan your website to get one.
                </p>
              </>
            )}
          </div>

          <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm lg:col-span-2">
            <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
              <h2 className="text-base font-semibold text-slate-950">
                What to do first
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {getFirstStep(counts)}
              </p>
              {topOpportunity && (
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  Biggest opportunity:{" "}
                  <span className="font-medium text-slate-700">
                    {topOpportunity.title}
                  </span>{" "}
                  — {topOpportunity.why}
                </p>
              )}
            </div>

            <CounterRow counts={counts} />
          </section>
        </div>

        {/* Reassurance: fixes done + honest expectations */}
        {doneCount > 0 && (
          <section className="mb-7 rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-6">
            <p className="text-sm leading-6 text-slate-600">
              <span className="font-medium text-slate-950">
                {doneCount} {plural(doneCount, "fix", "fixes")} approved so far.
              </span>{" "}
              Google usually reflects changes within 1–3 weeks — nothing to do
              while it catches up.
            </p>
          </section>
        )}

        {/* Quick actions */}
        <div className="mb-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            to="/issues"
            title="Open your Fix List"
            description="Everything we found, in plain English, sorted by what to do first."
          />
          <QuickAction
            to="/competitors"
            title="See competitor opportunities"
            description="A few ways other websites may be winning clicks you could have."
          />
          <QuickAction
            to="/developer"
            title="Have us do it for you"
            description="Prefer to hand it off? Get expert implementation from $500."
          />
        </div>

        {/* Submit URLs */}
        <div className="mb-7">
          <UrlSubmissionPanel
            project={project}
            onCompetitorAdded={() => {}}
            onWebsiteAdded={() => {}}
          />
        </div>

        {/* Scan history */}
        <CrawlHistory crawls={crawls} onDelete={handleCrawlDeleted} />
        </div>
      </div>
    </PullToRefresh>
  );
}