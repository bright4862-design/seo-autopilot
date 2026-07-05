import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import IssueDetailModal from "@/components/issues/IssueDetailModal";
import {
  Search, CheckCircle2, Bell, Wrench, ChevronRight, RefreshCw, Loader2, Sparkles, ListChecks,
} from "lucide-react";

const CATEGORIES = [
  {
    key: "auto_fixed",
    title: "Fixes prepared",
    subtitle: "We prepared these simple fixes for your review.",
    empty: "Nothing here yet. Run a scan to find quick wins we can handle for you.",
    icon: CheckCircle2,
    iconBg: "bg-green-100 text-green-600",
    countText: "text-green-600",
    badge: "bg-green-50 text-green-700 border-green-200",
  },
  {
    key: "needs_approval",
    title: "Needs your approval",
    subtitle: "We've prepared a fix — just review and approve.",
    empty: "You're all caught up — no fixes waiting for your approval.",
    icon: Bell,
    iconBg: "bg-amber-100 text-amber-600",
    countText: "text-amber-600",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
  },
  {
    key: "needs_developer",
    title: "Needs a developer",
    subtitle: "These need a developer to fix. We'll guide you through it.",
    empty: "No developer work needed right now.",
    icon: Wrench,
    iconBg: "bg-purple-100 text-purple-600",
    countText: "text-purple-600",
    badge: "bg-purple-50 text-purple-700 border-purple-200",
  },
];

export default function FixList() {
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIssue, setSelectedIssue] = useState(null);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        setProject(projects[0]);
        const iss = await base44.entities.SeoIssue.filter({ project_id: projects[0].id });
        setIssues(iss);
      }
      setLoading(false);
    };
    load();
  }, []);

  const handleStatusUpdate = async (issueId, newStatus) => {
    await base44.entities.SeoIssue.update(issueId, { status: newStatus });
    setIssues(prev => prev.map(i => (i.id === issueId ? { ...i, status: newStatus } : i)));
    if (selectedIssue?.id === issueId) setSelectedIssue(prev => ({ ...prev, status: newStatus }));
  };

  const startScan = () => navigate("/crawl-status?autostart=1");

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-2xl border border-gray-100 p-10 text-center">
          <Search className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <h3 className="font-semibold text-gray-800 mb-1">Let's scan your website</h3>
          <p className="text-sm text-gray-500 mb-5">Add your business and website to get your first Fix List.</p>
          <Button onClick={() => navigate("/onboarding")} className="gradient-primary text-white border-0">
            Add Your Website
          </Button>
        </div>
      </div>
    );
  }

  const counts = CATEGORIES.reduce((acc, c) => {
    acc[c.key] = issues.filter(i => i.status === c.key).length;
    return acc;
  }, {});

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ListChecks className="w-6 h-6 text-blue-600" /> Your Fix List
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {project.business_name} · {project.website_url}
          </p>
        </div>
        <Button onClick={startScan} className="gradient-primary text-white border-0">
          <RefreshCw className="w-4 h-4 mr-2" /> Run New Scan
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {CATEGORIES.map(c => (
          <div key={c.key} className="bg-white rounded-xl border border-gray-100 p-4 text-center">
            <div className={`text-2xl font-bold ${c.countText}`}>{counts[c.key]}</div>
            <div className="text-xs text-gray-500 mt-1">{c.title}</div>
          </div>
        ))}
      </div>

      {issues.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-100 p-10 text-center">
          <Sparkles className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <h3 className="font-semibold text-gray-800 mb-1">No issues yet</h3>
          <p className="text-sm text-gray-500 mb-5">Run your first scan to see a list of simple fixes.</p>
          <Button onClick={startScan} className="gradient-primary text-white border-0">
            <Search className="w-4 h-4 mr-2" /> Scan My Website
          </Button>
        </div>
      ) : (
        <div className="space-y-5">
          {CATEGORIES.map(cat => {
            const items = issues.filter(i => i.status === cat.key);
            return (
              <div key={cat.key} className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
                <div className="flex items-center gap-3 p-4 border-b border-gray-50">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${cat.iconBg}`}>
                    <cat.icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h2 className="font-semibold text-gray-800">{cat.title}</h2>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cat.badge}`}>
                        {items.length}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">{cat.subtitle}</p>
                  </div>
                </div>
                {items.length === 0 ? (
                  <p className="text-sm text-gray-400 px-4 py-6 text-center">{cat.empty}</p>
                ) : (
                  <div className="divide-y divide-gray-50">
                    {items.map(issue => (
                      <button
                        key={issue.id}
                        onClick={() => setSelectedIssue(issue)}
                        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-800 truncate">{issue.issue_title}</p>
                          <p className="text-xs text-gray-400 truncate">{issue.page_url}</p>
                        </div>
                        <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {selectedIssue && (
        <IssueDetailModal
          issue={selectedIssue}
          onClose={() => setSelectedIssue(null)}
          onStatusUpdate={handleStatusUpdate}
        />
      )}
    </div>
  );
}