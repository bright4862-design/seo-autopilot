import React from "react";
import { ChevronRight, Layers } from "lucide-react";
import { STATUS_BADGES, IMPACT_BADGES, pageName, fixTypeLabel } from "@/components/fixlist/fixDisplay";

const IMPACT_ORDER = ["critical", "high", "medium", "low"];

export default function GroupedFixCard({ group, onClick }) {
  const name = pageName(group[0].page_url);
  const impact = IMPACT_ORDER.find(p => group.some(i => i.priority === p)) || "medium";
  const types = [...new Set(group.map(fixTypeLabel))].join(", ");
  const [statusLabel, statusClass] = STATUS_BADGES[group[0].status] || ["Prepared", STATUS_BADGES.auto_fixed[1]];

  return (
    <button onClick={onClick} className="w-full text-left px-4 py-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
            Improve your {name}
          </p>
          <p className="text-xs text-gray-400 truncate mt-0.5">{group[0].page_url}</p>
          <p className="text-xs text-gray-500 mt-1.5">
            {group.length} recommendations prepared for this page · Prepared fixes: {types}
          </p>
          <div className="flex flex-wrap gap-1.5 mt-2.5">
            <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${statusClass}`}>{statusLabel}</span>
            <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${IMPACT_BADGES[impact]}`}>{impact} impact</span>
          </div>
        </div>
        <span className="flex items-center gap-1 text-xs font-medium text-blue-600 flex-shrink-0 mt-1">
          Review <ChevronRight className="w-3.5 h-3.5" />
        </span>
      </div>
    </button>
  );
}