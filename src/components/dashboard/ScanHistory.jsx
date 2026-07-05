import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";

export default function ScanHistory({ projectId, currentSeoScore }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const recent = await base44.entities.CrawlJob.filter({ project_id: projectId }, "-created_date", 5);
        setJobs(recent);
      } catch (e) {
        console.error("Failed to load scan history", e);
      }
      setLoading(false);
    };
    if (projectId) load();
  }, [projectId]);

  if (loading || jobs.length === 0) return null;

  const formatDate = (job) => {
    const d = job.completed_at || job.started_at || job.created_date;
    return d ? new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—";
  };

  const statusLabel = (job) => job.status === "complete" ? "Complete" : job.status === "failed" ? "Could not complete" : "In progress";

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
        <h2 className="text-base font-semibold text-slate-950">Scan history</h2>
        <p className="mt-1 text-sm text-slate-500">Your last {jobs.length} {jobs.length === 1 ? "scan" : "scans"}.</p>
      </div>
      <div className="divide-y divide-slate-100">
        {jobs.map((job, i) => {
          const isComplete = job.status === "complete";
          const isFailed = job.status === "failed";
          const score = typeof job.seo_score === "number" ? job.seo_score : i === 0 && typeof currentSeoScore === "number" ? currentSeoScore : null;
          return (
            <div key={job.id} className="grid gap-2 px-5 py-4 text-sm sm:grid-cols-[1fr_110px_140px_90px] sm:items-center sm:px-6">
              <div><span className="text-slate-950">{formatDate(job)}</span><span className="ml-2 text-slate-400">{statusLabel(job)}</span></div>
              <div className="text-slate-600"><span className="text-slate-400 sm:hidden">Pages: </span>{isComplete || isFailed ? (job.pages_crawled || 0) : "—"}</div>
              <div className="text-slate-600"><span className="text-slate-400 sm:hidden">Recommendations: </span>{isComplete ? (job.issues_found ?? 0) : "—"}</div>
              <div className="text-slate-600"><span className="text-slate-400 sm:hidden">Score: </span>{score !== null ? score : "—"}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}