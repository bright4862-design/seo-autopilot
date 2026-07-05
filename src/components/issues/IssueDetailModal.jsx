import React from "react";
import { Button } from "@/components/ui/button";
import { trackEvent } from "@/lib/analytics";
import { customerText, friendlyCategory, getStatusLabel } from "@/lib/friendlyLabels";
import { Copy, X } from "lucide-react";

export default function IssueDetailModal({ issue, onClose, onStatusUpdate }) {
  const nextStep = customerText(issue.ai_recommendation || issue.recommended_value || "Review this recommendation and decide the next step.");

  const copyRecommendation = async () => {
    await navigator.clipboard.writeText(nextStep);
    trackEvent("recommendation_copied", { recommendation_id: issue.id });
  };

  const requestHelp = () => {
    trackEvent("request_help_clicked", { recommendation_id: issue.id, source: "recommendation_modal" });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/25 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl shadow-slate-950/10" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div className="min-w-0">
            <p className="text-sm font-medium text-blue-600">{getStatusLabel(issue)}</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{customerText(issue.issue_title)}</h2>
            <p className="mt-1 truncate text-sm text-slate-400">{issue.page_url}</p>
          </div>
          <button aria-label="Close recommendation" onClick={onClose} className="rounded-full p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><X className="h-4 w-4" /></button>
        </div>

        <div className="divide-y divide-slate-100">
          <section className="px-6 py-5"><h3 className="text-sm font-semibold text-slate-950">What we found</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(issue.plain_english_explanation || "We found a website improvement worth reviewing.")}</p></section>
          <section className="px-6 py-5"><h3 className="text-sm font-semibold text-slate-950">Why it matters</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(issue.why_it_matters || "This may help customers and search engines understand your website more clearly.")}</p></section>
          <section className="px-6 py-5"><h3 className="text-sm font-semibold text-slate-950">Recommended next step</h3><p className="mt-2 text-sm leading-6 text-slate-600">{nextStep}</p></section>

          <details className="px-6 py-5">
            <summary className="cursor-pointer text-sm font-medium text-slate-500 hover:text-slate-950">More details</summary>
            <div className="mt-4 grid gap-3 text-sm leading-6 text-slate-600">
              <div><span className="text-slate-400">Area:</span> {friendlyCategory(issue.category)}</div>
              <div><span className="text-slate-400">Current:</span> {customerText(issue.current_value || "Not found")}</div>
              <div><span className="text-slate-400">Suggested:</span> {customerText(issue.recommended_value || nextStep)}</div>
              {issue.confidence_score > 0 && <div><span className="text-slate-400">Confidence:</span> {issue.confidence_score}%</div>}
            </div>
          </details>
        </div>

        <div className="flex flex-wrap gap-3 bg-slate-50/70 px-6 py-5">
          {issue.status === "needs_approval" || issue.status === "open" ? (
            <>
              <Button className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700" onClick={() => onStatusUpdate(issue.id, "approved")}>Approve</Button>
              <Button variant="outline" className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50" onClick={() => onStatusUpdate(issue.id, "rejected")}>Not now</Button>
            </>
          ) : (
            <Button variant="outline" className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50" onClick={() => onStatusUpdate(issue.id, "completed")}>Mark reviewed</Button>
          )}
          <Button variant="outline" className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50" onClick={copyRecommendation}><Copy className="mr-2 h-4 w-4" /> Copy</Button>
          <Button variant="outline" className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50" onClick={requestHelp}>Request help</Button>
        </div>
      </div>
    </div>
  );
}