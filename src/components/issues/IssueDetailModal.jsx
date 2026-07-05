import React from "react";
import { Button } from "@/components/ui/button";
import { customerText, friendlyCategory, getStatusLabel } from "@/lib/friendlyLabels";
import { Copy, X } from "lucide-react";

export default function IssueDetailModal({ issue, onClose, onStatusUpdate }) {
  const nextStep = customerText(issue.ai_recommendation || issue.recommended_value || "Review this recommendation and decide the next step.");

  const copyRecommendation = async () => {
    await navigator.clipboard.writeText(nextStep);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-0 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-6">
          <div className="min-w-0">
            <div className="mb-3 inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">{getStatusLabel(issue)}</div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-950">{customerText(issue.issue_title)}</h2>
            <p className="mt-1 truncate text-sm text-slate-400">{issue.page_url}</p>
          </div>
          <button aria-label="Close recommendation" onClick={onClose} className="rounded-full p-2 text-slate-500 hover:bg-slate-50"><X className="h-4 w-4" /></button>
        </div>

        <div className="space-y-6 p-6">
          <section><h3 className="text-sm font-semibold text-slate-950">What we found</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(issue.plain_english_explanation || "We found a website improvement worth reviewing.")}</p></section>
          <section><h3 className="text-sm font-semibold text-slate-950">Why it matters</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(issue.why_it_matters || "This may help customers and search engines understand your website more clearly.")}</p></section>
          <section><h3 className="text-sm font-semibold text-slate-950">Recommended next step</h3><p className="mt-2 text-sm leading-6 text-slate-600">{nextStep}</p></section>

          <details className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">Show technical details</summary>
            <div className="mt-4 space-y-3 text-sm text-slate-600">
              <div>Category: {friendlyCategory(issue.category)}</div>
              <div>Current: {customerText(issue.current_value || "Not found")}</div>
              <div>Recommended: {customerText(issue.recommended_value || nextStep)}</div>
              {issue.confidence_score > 0 && <div>Confidence: {issue.confidence_score}%</div>}
            </div>
          </details>

          <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-5">
            {issue.status === "needs_approval" || issue.status === "open" ? (
              <>
                <Button className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700" onClick={() => onStatusUpdate(issue.id, "approved")}>Approve</Button>
                <Button variant="outline" className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => onStatusUpdate(issue.id, "rejected")}>Not now</Button>
              </>
            ) : (
              <Button variant="outline" className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => onStatusUpdate(issue.id, "completed")}>Mark reviewed</Button>
            )}
            <Button variant="outline" className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={copyRecommendation}><Copy className="mr-2 h-4 w-4" /> Copy recommendation</Button>
            <Button variant="outline" className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Request help</Button>
          </div>
        </div>
      </div>
    </div>
  );
}