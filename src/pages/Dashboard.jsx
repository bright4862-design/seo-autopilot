import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import ScoreRing from "@/components/dashboard/ScoreRing";
import StatCard from "@/components/dashboard/StatCard";
import {
  CheckCircle2, Clock, AlertTriangle, Code, ArrowRightLeft,
  Globe, FileText, BarChart3, Search, Wrench, ExternalLink,
  Calendar, Zap
} from "lucide-react";

export default function Dashboard() {
  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);

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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <Zap className="w-12 h-12 text-blue-600 mb-4" />
        <h2 className="text-xl font-bold mb-2">Welcome to SEO Autopilot</h2>
        <p className="text-gray-500 mb-6">Let's get started by setting up your first project.</p>
        <Link to="/onboarding">
          <Button className="gradient-primary text-white border-0">Set Up Your Website</Button>
        </Link>
      </div>
    );
  }

  const autoFixed = issues.filter(i => i.status === "auto_fixed").length;
  const needsApproval = issues.filter(i => i.status === "needs_approval").length;
  const needsDev = issues.filter(i => i.status === "needs_developer").length;
  const errors404 = issues.filter(i => i.category === "404_error").length;
  const metaIssues = issues.filter(i => i.category === "meta_title" || i.category === "meta_description").length;
  const canonicalIssues = issues.filter(i => i.category === "canonical").length;
  const sitemapIssues = issues.filter(i => i.category === "sitemap").length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{project.business_name}</h1>
          <p className="text-sm text-gray-500 flex items-center gap-1.5 mt-1">
            <Globe className="w-3.5 h-3.5" />
            {project.website_url}
          </p>
        </div>
        <div className="flex gap-3">
          <Link to="/crawl-status">
            <Button className="gradient-primary text-white border-0">
              <Search className="w-4 h-4 mr-2" /> Run New Crawl
            </Button>
          </Link>
        </div>
      </div>

      {/* Score + summary */}
      <div className="grid lg:grid-cols-4 gap-6">
        <div className="bg-white rounded-2xl border border-gray-100 p-6 flex flex-col items-center justify-center relative">
          <ScoreRing score={project.seo_score || 62} />
          <div className="flex items-center gap-4 mt-4 text-xs text-gray-400">
            {project.last_crawl_at && (
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                Last: {new Date(project.last_crawl_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        <div className="lg:col-span-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard icon={CheckCircle2} label="Fixed automatically" value={autoFixed} color="green" subtitle="We handled these for you" />
          <StatCard icon={Clock} label="Needs your approval" value={needsApproval} color="amber" subtitle="Review and approve fixes" />
          <StatCard icon={Wrench} label="Needs a developer" value={needsDev} color="purple" subtitle="Clear instructions provided" />
          <StatCard icon={AlertTriangle} label="404 errors found" value={errors404} color="red" />
          <StatCard icon={FileText} label="Metadata issues" value={metaIssues} color="blue" />
          <StatCard icon={Globe} label="Canonical issues" value={canonicalIssues} color="cyan" />
        </div>
      </div>

      {/* Quick actions */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Link to="/issues" className="bg-white rounded-xl border border-gray-100 p-5 hover:shadow-md hover:shadow-gray-100 transition-all group">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">View Fix List</h3>
            <ExternalLink className="w-4 h-4 text-gray-400 group-hover:text-blue-600 transition-colors" />
          </div>
          <p className="text-sm text-gray-500">See all issues sorted by priority and status.</p>
        </Link>
        <Link to="/competitors" className="bg-white rounded-xl border border-gray-100 p-5 hover:shadow-md hover:shadow-gray-100 transition-all group">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">Competitor Gaps</h3>
            <ExternalLink className="w-4 h-4 text-gray-400 group-hover:text-blue-600 transition-colors" />
          </div>
          <p className="text-sm text-gray-500">See why competitors may be outranking you.</p>
        </Link>
        <Link to="/developer" className="bg-white rounded-xl border border-gray-100 p-5 hover:shadow-md hover:shadow-gray-100 transition-all group">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">Request Done-for-You Help</h3>
            <ExternalLink className="w-4 h-4 text-gray-400 group-hover:text-blue-600 transition-colors" />
          </div>
          <p className="text-sm text-gray-500">Get expert implementation starting at $500.</p>
        </Link>
      </div>

      {/* Recent issues needing attention */}
      {needsApproval > 0 && (
        <div className="bg-amber-50 border border-amber-100 rounded-xl p-5">
          <h3 className="font-semibold text-amber-900 mb-1 flex items-center gap-2">
            <Clock className="w-4 h-4" /> {needsApproval} fixes need your approval
          </h3>
          <p className="text-sm text-amber-700 mb-3">We found safe improvements but need your OK before applying them.</p>
          <Link to="/issues?status=needs_approval">
            <Button size="sm" variant="outline" className="border-amber-200 text-amber-700 hover:bg-amber-100">
              Review Now
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}