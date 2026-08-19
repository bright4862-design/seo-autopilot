import React, { useState } from "react";

/**
 * Canonical FixList work-queue presentation.
 *
 * This component is deliberately presentation-only: it receives already
 * contract-gated sections and never computes repair priority itself. The
 * caller keeps ownership of row actions and evidence drill-down rendering.
 */
export default function RepairSectionList({ sections = [], renderRow }) {
  const [showAllFixFirst, setShowAllFixFirst] = useState(false);
  const list = Array.isArray(sections) ? sections.filter(Boolean) : [];

  if (list.length === 0 || typeof renderRow !== "function") return null;

  return (
    <div className="mt-12">
      {list.map((section) => {
        const visibleRows = section.key === "fix_first" && showAllFixFirst
          ? [...(section.rows || []), ...(section.hiddenRows || [])]
          : section.rows || [];
        const hiddenCount = section.key === "fix_first" && !showAllFixFirst
          ? Number(section.hiddenCount || 0)
          : 0;

        return (
          <section key={section.key} className="mt-12 first:mt-0" aria-labelledby={`repair-section-${section.key}`}>
            <div className="flex items-baseline justify-between gap-4">
              <h2
                id={`repair-section-${section.key}`}
                className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint"
              >
                {section.label}
              </h2>
              <span className="text-[11px] tabular-nums text-ink-faint">{section.totalCount}</span>
            </div>

            <div className="mt-2">
              {visibleRows.map((row, index) => renderRow(row, index))}
            </div>

            {hiddenCount > 0 ? (
              <button
                type="button"
                onClick={() => setShowAllFixFirst(true)}
                className="mt-3 text-[13px] font-medium text-ink-muted underline decoration-hairline underline-offset-4 transition-colors hover:text-ink hover:no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                View {hiddenCount} more Fix first {hiddenCount === 1 ? "repair" : "repairs"}
              </button>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
