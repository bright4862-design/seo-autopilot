import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Shield, Users, Globe, Search, AlertTriangle, Clock, FileText, Settings } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function Admin() {
  const [projects, setProjects] = useState([]);
  const [crawlJobs, setCrawlJobs] = useState([]);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const [p, c, i] = await Promise.all([
        base44.entities.BusinessProject.list("-created_date", 50),
        base44.entities.CrawlJob.list("-created_date", 50),
        base44.entities.SeoIssue.list("-created_date", 50),
      ]);
      setProjects(p);
      setCrawlJobs(c);
      setIssues(i);
      setLoading(false);
    };
    load();
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  const failedCrawls = crawlJobs.filter(c => c.status === "failed");
  const pendingApprovals = issues.filter(i => i.status === "needs_approval");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Shield className="w-6 h-6 text-blue-600" /> Admin Dashboard
        </h1>
        <p className="text-sm text-gray-500 mt-1">Manage users, projects, and crawl operations</p>
      </div>

      {/* Stats */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { icon: Users, label: "Projects", value: projects.length, color: "bg-blue-50 text-blue-600" },
          { icon: Search, label: "Total Crawls", value: crawlJobs.length, color: "bg-green-50 text-green-600" },
          { icon: AlertTriangle, label: "Failed Crawls", value: failedCrawls.length, color: "bg-red-50 text-red-600" },
          { icon: Clock, label: "Pending Approvals", value: pendingApprovals.length, color: "bg-amber-50 text-amber-600" },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-4">
            <div className={`w-9 h-9 rounded-lg ${s.color} flex items-center justify-center mb-3`}>
              <s.icon className="w-4 h-4" />
            </div>
            <p className="text-2xl font-bold text-gray-900">{s.value}</p>
            <p className="text-sm text-gray-500">{s.label}</p>
          </div>
        ))}
      </div>

      <Tabs defaultValue="projects">
        <TabsList>
          <TabsTrigger value="projects">Projects</TabsTrigger>
          <TabsTrigger value="crawls">Crawl Jobs</TabsTrigger>
          <TabsTrigger value="approvals">Pending Approvals</TabsTrigger>
        </TabsList>

        <TabsContent value="projects" className="mt-4">
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            {projects.length === 0 ? (
              <div className="p-8 text-center text-gray-400">No projects yet</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50/50">
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Business</th>
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Website</th>
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Plan</th>
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Status</th>
                      <th className="text-left font-medium text-gray-500 px-4 py-3">SEO Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {projects.map(p => (
                      <tr key={p.id} className="border-b border-gray-50">
                        <td className="px-4 py-3 font-medium">{p.business_name}</td>
                        <td className="px-4 py-3"><code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{p.website_url}</code></td>
                        <td className="px-4 py-3"><span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">{p.subscription_plan}</span></td>
                        <td className="px-4 py-3"><span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">{p.status}</span></td>
                        <td className="px-4 py-3 font-medium">{p.seo_score || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="crawls" className="mt-4">
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            {crawlJobs.length === 0 ? (
              <div className="p-8 text-center text-gray-400">No crawl jobs yet</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50/50">
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Type</th>
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Status</th>
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Pages</th>
                      <th className="text-left font-medium text-gray-500 px-4 py-3">Started</th>
                    </tr>
                  </thead>
                  <tbody>
                    {crawlJobs.map(c => (
                      <tr key={c.id} className="border-b border-gray-50">
                        <td className="px-4 py-3">{c.crawl_type}</td>
                        <td className="px-4 py-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${c.status === "complete" ? "bg-green-100 text-green-700" : c.status === "failed" ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"}`}>
                            {c.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">{c.pages_crawled || 0} / {c.pages_found || 0}</td>
                        <td className="px-4 py-3 text-xs text-gray-500">{c.started_at ? new Date(c.started_at).toLocaleString() : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="approvals" className="mt-4">
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            {pendingApprovals.length === 0 ? (
              <div className="p-8 text-center text-gray-400">No pending approvals</div>
            ) : (
              <div className="divide-y divide-gray-50">
                {pendingApprovals.map(i => (
                  <div key={i.id} className="px-6 py-4">
                    <p className="text-sm font-medium text-gray-900">{i.issue_title}</p>
                    <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600 mt-1 inline-block">{i.page_url}</code>
                  </div>
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}