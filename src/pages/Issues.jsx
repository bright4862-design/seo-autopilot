import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PRIORITY_COLORS, STATUS_COLORS, STATUS_LABELS, CATEGORY_LABELS } from "@/lib/mockData";
import IssueDetailModal from "@/components/issues/IssueDetailModal";
import { Search, Filter, AlertTriangle } from "lucide-react";

export default function Issues() {
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState("all");
  const [filterStatus, setFilterStatus] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("status") || "all";
  });
  const [filterPriority, setFilterPriority] = useState("all");
  const [selectedIssue, setSelectedIssue] = useState(null);

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        const iss = await base44.entities.SeoIssue.filter({ project_id: projects[0].id });
        setIssues(iss);
      }
      setLoading(false);
    };
    load();
  }, []);

  const handleStatusUpdate = async (issueId, newStatus) => {
    await base44.entities.SeoIssue.update(issueId, { status: newStatus });
    setIssues(prev => prev.map(i => i.id === issueId ? { ...i, status: newStatus } : i));
    if (selectedIssue?.id === issueId) setSelectedIssue(prev => ({ ...prev, status: newStatus }));
  };

  const filtered = issues.filter(i => {
    if (search && !i.issue_title?.toLowerCase().includes(search.toLowerCase()) && !i.page_url?.toLowerCase().includes(search.toLowerCase())) return false;
    if (filterCategory !== "all" && i.category !== filterCategory) return false;
    if (filterStatus !== "all" && i.status !== filterStatus) return false;
    if (filterPriority !== "all" && i.priority !== filterPriority) return false;
    return true;
  });

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Issues & Fixes</h1>
        <p className="text-sm text-gray-500 mt-1">All SEO issues found on your site, sorted by priority</p>
      </div>

      {/* Summary badges */}
      <div className="flex flex-wrap gap-3">
        {[
          { label: "We fixed this", count: issues.filter(i => i.status === "auto_fixed").length, cls: "bg-green-50 text-green-700 border-green-200" },
          { label: "Needs your approval", count: issues.filter(i => i.status === "needs_approval").length, cls: "bg-amber-50 text-amber-700 border-amber-200" },
          { label: "Needs a developer", count: issues.filter(i => i.status === "needs_developer").length, cls: "bg-purple-50 text-purple-700 border-purple-200" },
          { label: "Open", count: issues.filter(i => i.status === "open").length, cls: "bg-gray-50 text-gray-700 border-gray-200" },
        ].map(b => (
          <span key={b.label} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${b.cls}`}>
            {b.label}: {b.count}
          </span>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input placeholder="Search issues or URLs..." className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={filterCategory} onValueChange={setFilterCategory}>
          <SelectTrigger className="w-full sm:w-44"><SelectValue placeholder="Category" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-full sm:w-44"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            {Object.entries(STATUS_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filterPriority} onValueChange={setFilterPriority}>
          <SelectTrigger className="w-full sm:w-36"><SelectValue placeholder="Priority" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Priorities</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Issues table */}
      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-gray-300" />
            <p className="font-medium">No issues found</p>
            <p className="text-sm">Try adjusting your filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/50">
                  <th className="text-left font-medium text-gray-500 px-4 py-3">Issue</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3 hidden md:table-cell">Page</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3">Category</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3">Priority</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(issue => (
                  <tr key={issue.id} className="border-b border-gray-50 hover:bg-blue-50/30 cursor-pointer transition-colors" onClick={() => setSelectedIssue(issue)}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900 truncate max-w-xs">{issue.issue_title}</p>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">{issue.page_url}</code>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-gray-600">{CATEGORY_LABELS[issue.category] || issue.category}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${PRIORITY_COLORS[issue.priority]}`}>
                        {issue.priority}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[issue.status]}`}>
                        {STATUS_LABELS[issue.status]}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

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