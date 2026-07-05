import React from "react";
import { customerText, getPriorityLabel, getStatusLabel } from "@/lib/friendlyLabels";

export default function RecommendationCard({ item, onReview }) {
  return (
    <button
      onClick={() => onReview(item)}
      className="group w-full border-b border-slate-100 px-5 py-5 text-left transition hover:bg-slate-50/70 last:border-b-0"
    >
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h3 className="text-base font-medium text-slate-950">
            {customerText(item.group_title || item.issue_title)}
          </h3>
          <p className="mt-1 truncate text-sm text-slate-400">{item.page_url}</p>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600">
            {customerText(item.summary || item.plain_english_explanation)}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
              {getStatusLabel(item)}
            </span>
            {item.priority && (
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                {getPriorityLabel(item.priority)}
              </span>
            )}
          </div>
        </div>
        <span className="shrink-0 text-sm font-medium text-blue-600 group-hover:text-blue-700">Review</span>
      </div>
    </button>
  );
}