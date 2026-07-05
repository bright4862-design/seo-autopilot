import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { History } from "lucide-react";

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

  return (
    <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
      <div className="flex items-center gap-3 p-4 border-b border-gray-50">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-blue-100 text-blue-600">
          <History className="w-4 h-4" />
        </div>
        <div>
          <h2 className="font-semibold text-gray-800">Scan history</h2>
          <p className="text-xs text-gray-500">Your last {jobs.length} {jobs.length === 1 ? "scan" : "scans"}</p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[480px]">
          <thead>
            <tr className="border-b border-gray-50 bg-gray-50/50">
              <th className="text-left font-medium text-gray-500 px-4 py-2.5">Scan date</th>
              <th className="text-left font-medium text-gray-500 px-4 py-2.5">Pages scanned</th>
              <th className="text-left font-medium text-gray-500 px-4 py-2.5">Improvements found</th>
              <th className="text-left font-medium text-gray-500 px-4 py-2.5">Status</th>
              <th className="text-left font-medium text-gray-500 px-4 py-2.5">Health score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {jobs.map((job, i) => {
              const isComplete = job.status === "complete";
              const isFailed = job.status === "failed";
              const score = typeof job.seo_score === "number"
                ? job.seo_score
                : i === 0 && typeof currentSeoScore === "number" ? currentSeoScore : null;
              return (
                <tr key={job.id} className="hover:bg-gray-50/50">
                  <td className="px-4 py-3 text-gray-700 whitespace-nowrap">{formatDate(job)}</td>
                  <td className="px-4 py-3 text-gray-700">{isComplete || isFailed ? (job.pages_crawled || 0) : "—"}</td>
                  <td className="px-4 py-3 text-gray-700">{isComplete ? (job.issues_found ?? 0) : "—"}</td>
                  <td className="px-4 py-3">
                    {isComplete ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">Completed</span>
                    ) : isFailed ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200">Failed</span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-50 text-gray-500 border border-gray-200">In progress</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-700">{score !== null ? score : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}