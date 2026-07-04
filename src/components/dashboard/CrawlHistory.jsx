import React, { useState } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Clock, Trash2, Loader2, CheckCircle2, AlertCircle } from "lucide-react";

const STATUS_LABELS = {
  queued: "Queued",
  crawling_html: "Crawling HTML",
  rendering_js: "Rendering JS",
  checking_metadata: "Checking Metadata",
  checking_canonicals: "Checking Canonicals",
  checking_sitemap: "Checking Sitemap",
  checking_redirects: "Checking Redirects",
  benchmarking_competitors: "Benchmarking Competitors",
  generating_recommendations: "Generating Recommendations",
  complete: "Complete",
  failed: "Failed",
};

export default function CrawlHistory({ crawls, onDelete }) {
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState("");

  const handleDelete = async (id) => {
    setError("");
    setDeletingId(id);
    try {
      await base44.entities.CrawlJob.delete(id);
      onDelete && onDelete(id);
    } catch (err) {
      setError(err.message || "Failed to delete crawl");
    } finally {
      setDeletingId(null);
    }
  };

  if (crawls.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-gray-100 p-6">
        <h3 className="font-semibold mb-1">Previous Crawls</h3>
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Clock className="w-8 h-8 text-gray-300 mb-2" />
          <p className="text-sm text-gray-400">No crawl history yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6">
      <h3 className="font-semibold mb-4">Previous Crawls</h3>
      {error && (
        <div className="mb-3 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">{error}</div>
      )}
      <div className="divide-y divide-gray-50">
        {crawls.map((c) => {
          const isComplete = c.status === "complete";
          const isFailed = c.status === "failed";
          return (
            <div key={c.id} className="flex items-center justify-between py-3">
              <div className="flex items-start gap-3 min-w-0">
                {isComplete ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                ) : isFailed ? (
                  <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                ) : (
                  <Clock className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800">
                    {STATUS_LABELS[c.status] || c.status}
                  </p>
                  <p className="text-xs text-gray-400">
                    {c.started_at ? new Date(c.started_at).toLocaleString() : "—"}
                    {c.pages_crawled ? ` · ${c.pages_crawled} pages` : ""}
                  </p>
                </div>
              </div>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => handleDelete(c.id)}
                disabled={deletingId === c.id}
                className="text-gray-400 hover:text-red-600 hover:bg-red-50"
                title="Delete crawl"
              >
                {deletingId === c.id ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}