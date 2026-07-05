import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import IssueDetailModal from "@/components/issues/IssueDetailModal";
import ScanHistory from "@/components/dashboard/ScanHistory";
import GroupedFixModal from "@/components/fixlist/GroupedFixModal";
import RecommendationCard from "@/components/fixlist/RecommendationCard";
import { groupIssuesByPage } from "@/lib/friendlyLabels";

const CATEGORIES = [
  { key: "auto_fixed", title: "Prepared", subtitle: "Ready for you to review.", empty: "Nothing is prepared yet." },
  { key: "needs_approval", title: "Needs review", subtitle: "Recommendations for you to approve or skip.", empty: "Nothing needs review right now." },
  { key: "needs_developer", title: "May need help", subtitle: "Larger improvements for a website editor or done-for-you help.", empty: "No larger improvements found right now." },
];

export default function FixList() {
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [selectedGroup, setSelectedGroup] = useState(null);

  useEffect(() => {
    trackEvent("fix_list_viewed");
    const load = async () => {
      const me = await base44.auth.me();
      const activeProjectId = window.localStorage.getItem("active_project_id");
      let activeProject = null;

      if (activeProjectId) {
        try {
          activeProject = await base44.entities.BusinessProject.get(activeProjectId);
        } catch (e) {}
      }

      if (!activeProject) {
        const projects = await base44.entities.BusinessProject.list("-last_crawl_at", 10);
        activeProject = projects.find((item) => item.owner_user_id === me.id || item.created_by_id === me.id) || projects[0];
      }

      if (activeProject) {
        setProject(activeProject);
        const data = await base44.entities.SeoIssue.filter({ project_id: activeProject.id, owner_user_id: me.id });
        setIssues(data);
      }
      setLoading(false);
    };
    load();
  }, []);

  const handleStatusUpdate = async (issueId, newStatus) => {
    await base44.entities.SeoIssue.update(issueId, { status: newStatus });
    const eventName = newStatus === "approved" ? "recommendation_approved" : newStatus === "rejected" ? "recommendation_rejected" : newStatus === "completed" ? "recommendation_marked_reviewed" : null;
    if (eventName) trackEvent(eventName, { recommendation_id: issueId, status: newStatus });
    setIssues((prev) => prev.map((issue) => (issue.id === issueId ? { ...issue, status: newStatus } : issue)));
    if (selectedIssue?.id === issueId) setSelectedIssue((prev) => ({ ...prev, status: newStatus }));
  };

  const startScan = () => navigate("/crawl-status");
  const openItem = (item) => {
    trackEvent("recommendation_opened", { recommendation_id: item.id, grouped: Boolean(item.grouped), count: item.recommendations?.length || 1 });
    item.grouped ? setSelectedGroup(item.recommendations) : setSelectedIssue(item);
  };

  if (loading) {
    return <div className="flex h-64 items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" /></div>;
  }

  const counts = {
    auto_fixed: issues.filter((issue) => issue.status === "auto_fixed").length,
    needs_approval: issues.filter((issue) => issue.status === "needs_approval").length,
    needs_developer: issues.filter((issue) => issue.status === "needs_developer").length,
  };

  const firstStep = counts.needs_approval > 0
    ? "Start by reviewing the recommendations that need your approval."
    : counts.needs_developer > 0
      ? "Start with the improvements that may need extra help."
      : counts.auto_fixed > 0
        ? "Start by reviewing your prepared recommendations."
        : "Your scan looks clean based on the website content we reviewed.";

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-6 lg:py-12">
        <div className="mb-8 flex flex-col items-start justify-between gap-5 sm:flex-row">
          <div>
            <p className="text-sm font-medium text-blue-600">Website recommendations</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Fix List</h1>
            <p className="mt-2 text-base leading-7 text-slate-500">Clear next steps for {project?.business_name || "your website"}.</p>
          </div>
          <div className="flex items-center gap-3">
            <Button asChild variant="outline" className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50">
              <Link to="/assistant">Ask AI</Link>
            </Button>
            <Button onClick={startScan} className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">Scan Website</Button>
          </div>
        </div>

        {!project ? (
          <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">Add your website to start.</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">We’ll prepare simple recommendations in minutes.</p>
            <Button onClick={startScan} className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">Scan Website</Button>
          </div>
        ) : (
          <>
            <section className="mb-7 overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
                <h2 className="text-base font-semibold text-slate-950">What to do first</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{firstStep}</p>
              </div>
              <div className="divide-y divide-slate-100">
                <div className="flex items-center justify-between px-5 py-4 sm:px-6"><span className="text-sm text-slate-500">Prepared</span><span className="text-lg font-semibold text-slate-950">{counts.auto_fixed}</span></div>
                <div className="flex items-center justify-between px-5 py-4 sm:px-6"><span className="text-sm text-slate-500">Needs review</span><span className="text-lg font-semibold text-slate-950">{counts.needs_approval}</span></div>
                <div className="flex items-center justify-between px-5 py-4 sm:px-6"><span className="text-sm text-slate-500">May need help</span><span className="text-lg font-semibold text-slate-950">{counts.needs_developer}</span></div>
              </div>
            </section>

            {issues.length === 0 ? (
              <div className="rounded-3xl border border-slate-200/80 bg-white p-10 text-center shadow-sm">
                <h2 className="text-lg font-semibold text-slate-950">{project.last_crawl_at ? "Your scan looks clean" : "No recommendations yet"}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{project.last_crawl_at ? "Based on the website content we reviewed, no improvements are needed right now." : "Run your first scan to see recommended improvements."}</p>
                <Button onClick={startScan} className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">Scan Website</Button>
              </div>
            ) : (
              <div className="space-y-7">
                {CATEGORIES.map((category) => {
                  const grouped = groupIssuesByPage(issues.filter((issue) => issue.status === category.key));
                  return (
                    <section key={category.key} className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
                      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
                        <h2 className="text-base font-semibold text-slate-950">{category.title}</h2>
                        <p className="mt-1 text-sm text-slate-500">{category.subtitle}</p>
                      </div>
                      {grouped.length === 0 ? <p className="px-5 py-5 text-sm text-slate-500 sm:px-6">{category.empty}</p> : grouped.map((item) => <RecommendationCard key={item.id} item={item} onReview={openItem} />)}
                    </section>
                  );
                })}
              </div>
            )}

            <div className="mt-8"><ScanHistory projectId={project.id} currentSeoScore={project.seo_score} /></div>
          </>
        )}
      </div>

      {selectedIssue && <IssueDetailModal issue={selectedIssue} onClose={() => setSelectedIssue(null)} onStatusUpdate={handleStatusUpdate} />}
      {selectedGroup && <GroupedFixModal group={selectedGroup} onClose={() => setSelectedGroup(null)} onStatusUpdate={handleStatusUpdate} />}
    </div>
  );
}