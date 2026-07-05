import React from "react";
import { customerText, getPriorityLabel, getStatusLabel } from "@/lib/friendlyLabels";

export default function RecommendationCard({ item, onReview }) {
  return (
    <button
      onClick={() => onReview(item)}
      className="group w-full border-b border-slate-100 px-5 py-4 text-left transition hover:bg-slate-50/80 last:border-b-0 sm:px-6"
    >
      <div className="flex items-start justify-between gap-5">
        <div className="min-w-0">
          <h3 className="text-[15px] font-medium text-slate-950">{customerText(item.group_title || item.issue_title)}</h3>
          <p className="mt-1 truncate text-sm text-slate-400">{item.page_url}</p>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600">{customerText(item.summary || item.plain_english_explanation)}</p>
          <p className="mt-2 text-xs font-medium text-slate-400">{getStatusLabel(item)}{item.priority ? ` · ${getPriorityLabel(item.priority)}` : ""}</p>
        </div>
        <span className="shrink-0 pt-0.5 text-sm font-medium text-blue-600 group-hover:text-blue-700">Review</span>
      </div>
    </button>
  );
}