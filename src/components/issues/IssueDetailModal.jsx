import React from "react";
import { Button } from "@/components/ui/button";
import { trackEvent } from "@/lib/analytics";
import { customerText, getStatusLabel } from "@/lib/friendlyLabels";
import { evidenceLink } from "@/lib/evidenceUrl";
import { ChevronLeft, Copy, X } from "lucide-react";

export default function IssueDetailModal({ issue, onClose, onStatusUpdate }) {
  const nextStep = customerText(issue.ai_recommendation || issue.recommended_value || "Review this recommendation and decide the next step.");
  const affectedPages = Array.isArray(issue.affected_pages) ? issue.affected_pages.filter(Boolean) : [];
  const details = issue.details && typeof issue.details === "object" ? issue.details : {};
  const affectedCount = details.affected_count || affectedPages.length;
  const siteOrigin = issue.website_url || issue.scope_origin || "";

  const copyRecommendation = async () => {
    await navigator.clipboard.writeText(nextStep);
    trackEvent("recommendation_copied", { recommendation_id: issue.id });
  };

  const copyAffectedUrl = async (page) => {
    const link = evidenceLink(page, siteOrigin);
    const value = link.href || page;
    if (!value) return;
    await navigator.clipboard.writeText(value);
    trackEvent("affected_page_url_copied", { recommendation_id: issue.id });
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
          <div className="flex shrink-0 items-center gap-2">
            <button aria-label="Back" onClick={onClose} className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-950 sm:hidden"><ChevronLeft className="h-4 w-4" /> Back</button>
            <button aria-label="Close recommendation" onClick={onClose} className="rounded-full p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><X className="h-4 w-4" /></button>
          </div>
        </div>

        <div className="divide-y divide-slate-100">
          <section className="px-6 py-5"><h3 className="text-sm font-semibold text-slate-950">What we found</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(issue.plain_english_explanation || "We found a website improvement worth reviewing.")}</p></section>
          <section className="px-6 py-5"><h3 className="text-sm font-semibold text-slate-950">Why it matters</h3><p className="mt-2 text-sm leading-6 text-slate-600">{customerText(issue.why_it_matters || "This may help customers and search engines understand your website more clearly.")}</p></section>
          <section className="px-6 py-5"><h3 className="text-sm font-semibold text-slate-950">Recommended next step</h3><p className="mt-2 text-sm leading-6 text-slate-600">{nextStep}</p></section>

          {affectedPages.length > 0 && (
            <section className="px-6 py-5">
              <h3 className="text-sm font-semibold text-slate-950">Affected pages</h3>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-600">
                {affectedPages.map((page, index) => {
                  const link = evidenceLink(page, siteOrigin);
                  return (
                    <li key={`${page}-${index}`} className="flex items-start justify-between gap-3">
                      <div className="min-w-0 break-all">
                        {link.isLinkable ? (
                          <a
                            href={link.href}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={link.title}
                            aria-label={link.linkName}
                            className="font-medium text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-950"
                          >
                            {link.label}
                          </a>
                        ) : (
                          <span title={link.title || undefined}>{link.label}</span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => copyAffectedUrl(page)}
                        className="shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-50 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                        aria-label={`Copy URL: ${link.label}`}
                      >
                        <Copy className="h-3.5 w-3.5" />
                        Copy URL
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          <details className="px-6 py-5">
            <summary className="cursor-pointer text-sm font-medium text-slate-500 hover:text-slate-950">Show technical details</summary>
            <div className="mt-4 grid gap-3 text-sm leading-6 text-slate-600">
              <div><span className="text-slate-400">Category:</span> {issue.category}</div>
              {details.original_category && <div><span className="text-slate-400">Original category:</span> {details.original_category}</div>}
              {affectedCount > 0 && <div><span className="text-slate-400">Affected count:</span> {affectedCount}</div>}
              {details.technical_term && <div><span className="text-slate-400">Technical term:</span> {details.technical_term}</div>}
              {typeof details.html_only_scan === "boolean" && <div><span className="text-slate-400">HTML-only scan:</span> {details.html_only_scan ? "Yes" : "No"}</div>}
              {typeof details.javascript_rendering_used === "boolean" && <div><span className="text-slate-400">JavaScript rendering used:</span> {details.javascript_rendering_used ? "Yes" : "No"}</div>}
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