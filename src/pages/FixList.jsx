import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import IssueDetailModal from "@/components/issues/IssueDetailModal";
import ScanHistory from "@/components/dashboard/ScanHistory";
import WhatToDoFirst from "@/components/dashboard/WhatToDoFirst";
import FixCard from "@/components/fixlist/FixCard";
import GroupedFixCard from "@/components/fixlist/GroupedFixCard";
import GroupedFixModal from "@/components/fixlist/GroupedFixModal";

const CATEGORIES = [
  {
    key: "auto_fixed",
    title: "Prepared fixes",
    subtitle: "Simple improvements we prepared for your review.",
    empty: "Nothing here yet. Run a scan to find quick wins.",
  },
  {
    key: "needs_approval",
    title: "Needs your approval",
    subtitle: "Review and approve these recommended improvements.",
    empty: "No fixes waiting for your approval.",
  },
  {
    key: "needs_developer",
    title: "Needs a developer",
    subtitle: "These need a developer. We'll guide you through it.",
    empty: "No developer work needed right now.",
  },
];

const COUNTERS = [
  { key: "auto_fixed", label: "Prepared" },
  { key: "needs_approval", label: "Needs approval" },
  { key: "needs_developer", label: "Needs developer" },
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

  const startScan = () => navigate("/crawl-status");

  // Group multiple prepared fixes for the same page into one card
  const renderItems = (catKey, items) => {
    if (catKey === "auto_fixed") {
      const byPage = {};
      items.forEach(i => { (byPage[i.page_url] = byPage[i.page_url] || []).push(i); });
      return Object.entries(byPage).map(([url, group]) =>
        group.length > 1
          ? <GroupedFixCard key={url} group={group} onClick={() => setSelectedGroup(group)} />
          : <FixCard key={group[0].id} issue={group[0]} onClick={() => setSelectedIssue(group[0])} />
      );
    }
    return items.map(issue => (
      <FixCard key={issue.id} issue={issue} onClick={() => setSelectedIssue(issue)} />
    ));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="max-w-2xl mx-auto pt-16 text-center">
        <h3 className="text-xl font-semibold text-gray-900 mb-2">Add your website to start your first scan.</h3>
        <p className="text-sm text-gray-500 mb-6">We'll find simple SEO improvements in minutes.</p>
        <Button onClick={startScan}>Scan Website</Button>
      </div>
    );
  }

  const counts = CATEGORIES.reduce((acc, c) => {
    acc[c.key] = issues.filter(i => i.status === c.key).length;
    return acc;
  }, {});

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Your Fix List</h1>
          <p className="text-sm text-gray-500 mt-1.5">
            Recommended SEO improvements for {project.business_name}.
          </p>
        </div>
        <Button onClick={startScan}>Scan Website</Button>
      </div>

      <WhatToDoFirst counts={counts} />

      <div className="grid grid-cols-3 divide-x divide-gray-100 bg-white rounded-xl border border-gray-100 shadow-sm">
        {COUNTERS.map(c => (
          <div key={c.key} className="p-4 text-center">
            <div className="text-2xl font-semibold text-gray-900">{counts[c.key]}</div>
            <div className="text-xs text-gray-500 mt-0.5">{c.label}</div>
          </div>
        ))}
      </div>

      {issues.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-10 text-center">
          {project.last_crawl_at ? (
            <>
              <h3 className="font-semibold text-gray-900 mb-1">Your scan looks clean</h3>
              <p className="text-sm text-gray-500">Based on the accessible HTML we reviewed, no improvements are needed right now.</p>
              <p className="text-sm text-gray-500 mb-6">Want a deeper review? Add competitors or request a manual review.</p>
            </>
          ) : (
            <>
              <h3 className="font-semibold text-gray-900 mb-1">No recommendations yet</h3>
              <p className="text-sm text-gray-500 mb-6">Run your first scan to see recommended improvements.</p>
            </>
          )}
          <Button onClick={startScan}>Scan Website</Button>
        </div>
      ) : (
        <div className="space-y-8">
          {CATEGORIES.map(cat => {
            const items = issues.filter(i => i.status === cat.key);
            return (
              <section key={cat.key}>
                <div className="px-1 mb-3">
                  <div className="flex items-baseline gap-2">
                    <h2 className="text-base font-semibold text-gray-900">{cat.title}</h2>
                    <span className="text-sm text-gray-400">{items.length}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{cat.subtitle}</p>
                </div>
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
                  {items.length === 0 ? (
                    <p className="text-sm text-gray-400 px-5 py-6">{cat.empty}</p>
                  ) : (
                    <div className="divide-y divide-gray-50">
                      {renderItems(cat.key, items)}
                    </div>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}

      <ScanHistory projectId={project.id} currentSeoScore={project.seo_score} />

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
  );
}