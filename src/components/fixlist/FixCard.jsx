import React from "react";
import { ChevronRight } from "lucide-react";
import { STATUS_BADGES, IMPACT_BADGES } from "@/components/fixlist/fixDisplay";

export default function FixCard({ issue, onClick }) {
  const [statusLabel, statusClass] = STATUS_BADGES[issue.status] || [issue.status, "bg-gray-50 text-gray-600 border-gray-200"];
  return (
    <button onClick={onClick} className="w-full text-left px-4 py-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800">{issue.issue_title}</p>
          <p className="text-xs text-gray-400 truncate mt-0.5">{issue.page_url}</p>
          {issue.plain_english_explanation && (
            <p className="text-xs text-gray-500 mt-1.5 line-clamp-2">{issue.plain_english_explanation}</p>
          )}
          <div className="flex flex-wrap gap-1.5 mt-2.5">
            <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${statusClass}`}>{statusLabel}</span>
            {issue.priority && (
              <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${IMPACT_BADGES[issue.priority] || IMPACT_BADGES.low}`}>
                {issue.priority} impact
              </span>
            )}
          </div>
        </div>
        <span className="flex items-center gap-1 text-xs font-medium text-blue-600 flex-shrink-0 mt-1">
          Review recommendation <ChevronRight className="w-3.5 h-3.5" />
        </span>
      </div>
    </button>
  );
}