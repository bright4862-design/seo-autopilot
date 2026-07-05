import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import IssueDetailModal from "@/components/issues/IssueDetailModal";
import ScanHistory from "@/components/dashboard/ScanHistory";
import GroupedFixModal from "@/components/fixlist/GroupedFixModal";
import RecommendationCard from "@/components/fixlist/RecommendationCard";
import { groupIssuesByPage } from "@/lib/friendlyLabels";

const CATEGORIES = [
  { key: "auto_fixed", title: "Prepared", subtitle: "Recommendations prepared for review.", empty: "Nothing is prepared yet." },
  { key: "needs_approval", title: "Needs review", subtitle: "Recommended improvements for you to approve or skip.", empty: "Nothing needs your review right now." },
  { key: "needs_developer", title: "May need help", subtitle: "Improvements that may need a website editor or done-for-you help.", empty: "No larger improvements found right now." },
];

export default function FixList() {
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [selectedGroup, setSelectedGroup] = useState(null);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        setProject(projects[0]);
        const data = await base44.entities.SeoIssue.filter({ project_id: projects[0].id });
        setIssues(data);
      }
      setLoading(false);
    };
    load();
  }, []);

  const handleStatusUpdate = async (issueId, newStatus) => {
    await base44.entities.SeoIssue.update(issueId, { status: newStatus });
    setIssues((prev) => prev.map((issue) => (issue.id === issueId ? { ...issue, status: newStatus } : issue)));
    if (selectedIssue?.id === issueId) setSelectedIssue((prev) => ({ ...prev, status: newStatus }));
  };

  const startScan = () => navigate("/crawl-status");
  const openItem = (item) => item.grouped ? setSelectedGroup(item.recommendations) : setSelectedIssue(item);

  if (loading) {
    return <div className="flex h-64 items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" /></div>;
  }

  const counts = {
    auto_fixed: issues.filter((issue) => issue.status === "auto_fixed").length,
    needs_approval: issues.filter((issue) => issue.status === "needs_approval").length,
    needs_developer: issues.filter((issue) => issue.status === "needs_developer").length,
  };

  const firstStep = counts.needs_approval > 0
    ? "Start by reviewing the items that need your approval."
    : counts.needs_developer > 0
      ? "Start with the improvements that may need help."
      : counts.auto_fixed > 0
        ? "Start by reviewing your prepared recommendations."
        : "Your scan looks clean based on the website content we reviewed.";

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-5xl px-6 py-10">
        <div className="mb-8 flex flex-col items-start justify-between gap-6 sm:flex-row">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Your Fix List</h1>
            <p className="mt-2 text-base text-slate-500">Recommended website improvements for {project?.business_name || "your business"}.</p>
          </div>
          <div className="flex items-center gap-3">
            <Button asChild variant="outline" className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
              <Link to="/assistant">Ask AI</Link>
            </Button>
            <Button onClick={startScan} className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700">Scan Website</Button>
          </div>
        </div>

        {!project ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <h2 className="text-lg font-semibold text-slate-950">Add your website to start your first scan.</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">We’ll prepare simple recommendations in minutes.</p>
            <Button onClick={startScan} className="mt-6 rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700">Scan Website</Button>
          </div>
        ) : (
          <>
            <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-base font-semibold text-slate-950">What to do first</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{firstStep}</p>
            </div>

            <div className="mb-8 grid grid-cols-3 gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
              <div className="rounded-xl px-4 py-3"><div className="text-2xl font-semibold text-slate-950">{counts.auto_fixed}</div><div className="text-sm text-slate-500">Prepared</div></div>
              <div className="rounded-xl px-4 py-3"><div className="text-2xl font-semibold text-slate-950">{counts.needs_approval}</div><div className="text-sm text-slate-500">Needs review</div></div>
              <div className="rounded-xl px-4 py-3"><div className="text-2xl font-semibold text-slate-950">{counts.needs_developer}</div><div className="text-sm text-slate-500">May need help</div></div>
            </div>

            {issues.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
                <h2 className="text-lg font-semibold text-slate-950">{project.last_crawl_at ? "Your scan looks clean" : "No recommendations yet"}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{project.last_crawl_at ? "Based on the website content we reviewed, no improvements are needed right now." : "Run your first scan to see recommended improvements."}</p>
                <Button onClick={startScan} className="mt-6 rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700">Scan Website</Button>
              </div>
            ) : (
              CATEGORIES.map((category) => {
                const grouped = groupIssuesByPage(issues.filter((issue) => issue.status === category.key));
                return (
                  <section key={category.key} className="mb-8 rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="border-b border-slate-100 px-5 py-4">
                      <h2 className="text-lg font-semibold text-slate-950">{category.title}</h2>
                      <p className="mt-1 text-sm text-slate-500">{category.subtitle}</p>
                    </div>
                    <div>
                      {grouped.length === 0 ? <p className="px-5 py-6 text-sm text-slate-500">{category.empty}</p> : grouped.map((item) => <RecommendationCard key={item.id} item={item} onReview={openItem} />)}
                    </div>
                  </section>
                );
              })
            )}

            <ScanHistory projectId={project.id} currentSeoScore={project.seo_score} />
          </>
        )}
      </div>

      {selectedIssue && <IssueDetailModal issue={selectedIssue} onClose={() => setSelectedIssue(null)} onStatusUpdate={handleStatusUpdate} />}
      {selectedGroup && <GroupedFixModal group={selectedGroup} onClose={() => setSelectedGroup(null)} onStatusUpdate={handleStatusUpdate} />}
    </div>
  );
}