import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import IssueDetailModal from "@/components/issues/IssueDetailModal";
import ScanHistory from "@/components/dashboard/ScanHistory";
import GroupedFixModal from "@/components/fixlist/GroupedFixModal";
import RecommendationCard from "@/components/fixlist/RecommendationCard";
import PullToRefresh from "@/components/layout/PullToRefresh";
import { groupIssuesByPage } from "@/lib/friendlyLabels";
import {
  ACTIVE_STATUSES,
  BUCKETS,
  countBuckets,
  getFirstStep,
  getIssueBucket,
  resolveActiveProject,
} from "@/lib/appModel";

// The three sections come from the shared model so the Dashboard and the
// Fix List always use the same titles and the same order.
const SECTIONS = BUCKETS;

function CounterRow({ counts }) {
  return (
    <div className="grid divide-y divide-slate-100 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
      {SECTIONS.map((section) => (
        <div
          key={section.key}
          className="flex items-center justify-between px-5 py-4 sm:block sm:px-6"
        >
          <p className="text-sm text-slate-500">{section.title}</p>
          <p className="text-xl font-semibold text-slate-950 sm:mt-1">
            {counts[section.key]}
          </p>
        </div>
      ))}
    </div>
  );
}

function EmptyProjectState({ onScan }) {
  return (
    <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
      <h2 className="text-lg font-semibold text-slate-950">
        Add your website to start.
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600">
        Enter your website and we&rsquo;ll prepare a simple Fix List.
      </p>
      <Button
        onClick={onScan}
        className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
      >
        Scan Website
      </Button>
    </div>
  );
}

function EmptyRecommendationsState({ project, onScan }) {
  const hasScanned = Boolean(project?.last_crawl_at);

  return (
    <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
      <h2 className="text-lg font-semibold text-slate-950">
        {hasScanned ? "Your scan looks clean" : "No recommendations yet"}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600">
        {hasScanned
          ? "Based on the website content we reviewed, no major recommendations are needed right now."
          : "Run a scan to get clear next steps for your website."}
      </p>
      <Button
        onClick={onScan}
        className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
      >
        Scan Website
      </Button>
    </div>
  );
}

function CompetitorOpportunities({ count }) {
  if (!count) return null;

  return (
    <section className="mb-7 rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-950">
            Competitor opportunities
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            We found a few ways other pages may be stronger.
          </p>
        </div>

        <Button
          asChild
          variant="outline"
          className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50"
        >
          <Link to="/competitors">View</Link>
        </Button>
      </div>
    </section>
  );
}

function RecommendationSection({ section, issues, onReview }) {
  const grouped = groupIssuesByPage(issues);

  if (grouped.length === 0) return null;

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">
              {section.title}
            </h2>
            <p className="mt-1 text-sm text-slate-500">{section.subtitle}</p>
          </div>

          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
            {grouped.length}
          </span>
        </div>
      </div>

      <div className="divide-y divide-slate-100">
        {grouped.map((item) => (
          <RecommendationCard
            key={item.id || `${item.page_url}-${item.issue_title}`}
            item={item}
            onReview={onReview}
          />
        ))}
      </div>
    </section>
  );
}

export default function FixList() {
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [competitorOpportunityCount, setCompetitorOpportunityCount] =
    useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [selectedGroup, setSelectedGroup] = useState(null);

  const loadData = async () => {
    try {
      const { user, project: activeProject } = await resolveActiveProject(base44);

      if (!activeProject) {
        setLoading(false);
        return;
      }

      setProject(activeProject);

      const [issueData, insights, keywordGaps] = await Promise.all([
        base44.entities.SeoIssue.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
        base44.entities.CompetitorInsight.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
        base44.entities.KeywordGapAnalysis.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
      ]);

      const visibleIssues = (issueData || []).filter((issue) =>
        ACTIVE_STATUSES.has(issue.status)
      );

      setIssues(visibleIssues);
      setCompetitorOpportunityCount(
        (insights?.length || 0) + (keywordGaps?.length || 0)
      );
    } catch (err) {
      console.warn("Could not load Fix List.", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    trackEvent("fix_list_viewed");
    loadData();
  }, []);

  const counts = useMemo(() => countBuckets(issues), [issues]);

  const issuesBySection = useMemo(() => {
    return {
      auto_fixed: issues.filter(
        (issue) => getIssueBucket(issue) === "auto_fixed"
      ),
      needs_approval: issues.filter(
        (issue) => getIssueBucket(issue) === "needs_approval"
      ),
      needs_developer: issues.filter(
        (issue) => getIssueBucket(issue) === "needs_developer"
      ),
    };
  }, [issues]);

  const firstStep = getFirstStep(counts);

  const startScan = () => {
    navigate("/crawl-status");
  };

  const openItem = (item) => {
    trackEvent("recommendation_opened", {
      recommendation_id: item.id,
      grouped: Boolean(item.grouped),
      count: item.recommendations?.length || 1,
    });

    if (item.grouped) {
      setSelectedGroup(item.recommendations || []);
    } else {
      setSelectedIssue(item);
    }
  };

  const handleStatusUpdate = async (issueId, newStatus) => {
    const previousIssues = issues;
    const previousSelectedIssue = selectedIssue;

    setIssues((previous) =>
      previous
        .map((issue) =>
          issue.id === issueId ? { ...issue, status: newStatus } : issue
        )
        .filter((issue) => ACTIVE_STATUSES.has(issue.status))
    );

    if (selectedIssue?.id === issueId) {
      setSelectedIssue((previous) =>
        previous ? { ...previous, status: newStatus } : previous
      );
    }

    try {
      await base44.entities.SeoIssue.update(issueId, { status: newStatus });

      const eventName =
        newStatus === "approved"
          ? "recommendation_approved"
          : newStatus === "rejected"
            ? "recommendation_rejected"
            : newStatus === "completed"
              ? "recommendation_marked_reviewed"
              : null;

      if (eventName) {
        trackEvent(eventName, {
          recommendation_id: issueId,
          status: newStatus,
        });
      }
    } catch (err) {
      console.warn("Could not update recommendation status.", err);
      setIssues(previousIssues);
      setSelectedIssue(previousSelectedIssue);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  return (
    <PullToRefresh onRefresh={loadData}>
      <div className="min-h-screen bg-[#F7F8FA] dark:bg-slate-950">
        <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8 flex flex-col items-start justify-between gap-5 sm:flex-row">
          <div>
            <p className="text-sm font-medium text-blue-600">
              Website recommendations
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              Fix List
            </h1>
            <p className="mt-2 text-base leading-7 text-slate-500">
              SEO Autopilot scans your website, reviews important pages, looks
              for competitor opportunities when possible, and prepares a simple
              Fix List.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Button
              asChild
              variant="outline"
              className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50"
            >
              <Link to="/assistant">Ask AI</Link>
            </Button>

            <Button
              onClick={startScan}
              className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
            >
              Scan Website
            </Button>
          </div>
        </div>

        {!project ? (
          <EmptyProjectState onScan={startScan} />
        ) : (
          <>
            <section className="mb-7 overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
                <h2 className="text-base font-semibold text-slate-950">
                  What to do first
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {firstStep}
                </p>
              </div>

              <CounterRow counts={counts} />
            </section>

            <CompetitorOpportunities count={competitorOpportunityCount} />

            {issues.length === 0 ? (
              <EmptyRecommendationsState project={project} onScan={startScan} />
            ) : (
              <div className="space-y-7">
                {SECTIONS.map((section) => (
                  <RecommendationSection
                    key={section.key}
                    section={section}
                    issues={issuesBySection[section.key]}
                    onReview={openItem}
                  />
                ))}
              </div>
            )}

            <div className="mt-8">
              <ScanHistory
                projectId={project.id}
                currentSeoScore={project.seo_score}
              />
            </div>
          </>
        )}
      </div>

      {selectedIssue && (
        <IssueDetailModal
          issue={selectedIssue}
          onClose={() => setSelectedIssue(null)}
          onStatusUpdate={handleStatusUpdate}
        />
      )}

        {selectedGroup && (
          <GroupedFixModal
            group={selectedGroup}
            onClose={() => setSelectedGroup(null)}
            onStatusUpdate={handleStatusUpdate}
          />
        )}
      </div>
    </PullToRefresh>
  );
}