import React, { useState } from "react";

import CanonicalRepairRow from "@/components/fixlist/CanonicalRepairRow";

const SECTION_HELP = Object.freeze({
  fix_first: "Start here.",
  important: "Significant repairs to tackle next.",
  improve: "Useful improvements after the important work.",
  review: "Worth checking; these may need your judgment.",
});

/**
 * Canonical FixList work-queue presentation.
 *
 * This component is deliberately presentation-only: it receives already
 * contract-gated sections and never computes repair priority itself.
 *
 * The compact canonical row owns the visible work-queue hierarchy. The caller's
 * existing `renderRow` output is preserved as expandable detail, so evidence,
 * instructions, and workflow actions can migrate without being duplicated into
 * a second implementation here.
 */
export default function RepairSectionList({ sections = [], renderRow }) {
  const [showAllFixFirst, setShowAllFixFirst] = useState(false);
  const list = Array.isArray(sections) ? sections.filter(Boolean) : [];

  if (list.length === 0 || typeof renderRow !== "function") return null;

  const repairCount = list.reduce((total, section) => total + Number(section.totalCount || 0), 0);

  return (
    <div className="mt-10 sm:mt-12" aria-labelledby="canonical-fixlist-heading">
      <div className="mb-8">
        <div className="flex items-baseline justify-between gap-4">
          <h2 id="canonical-fixlist-heading" className="text-[20px] font-semibold tracking-tight text-ink">
            Your FixList
          </h2>
          <span className="shrink-0 text-[12px] tabular-nums text-ink-faint">
            {repairCount} remaining
          </span>
        </div>
        <p className="mt-1.5 max-w-[52ch] text-[12px] leading-relaxed text-ink-faint">
          Work through the repairs in order. FixList verifies changes only after a later comparable scan.
        </p>
      </div>

      {list.map((section) => {
        const hiddenRows = section.key === "fix_first" ? section.hiddenRows || [] : [];
        const hasFixFirstOverflow = hiddenRows.length > 0;
        const visibleRows = section.key === "fix_first" && showAllFixFirst
          ? [...(section.rows || []), ...hiddenRows]
          : section.rows || [];
        const hiddenCount = section.key === "fix_first" && !showAllFixFirst
          ? Number(section.hiddenCount || hiddenRows.length || 0)
          : 0;
        const totalCount = Number(section.totalCount || 0);
        const help = SECTION_HELP[section.key] || "";

        return (
          <section key={section.key} className="mt-10 first:mt-0 sm:mt-12" aria-labelledby={`repair-section-${section.key}`}>
            <div className="flex items-baseline justify-between gap-4">
              <h3
                id={`repair-section-${section.key}`}
                className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint"
              >
                {section.label}
              </h3>
              <span className="text-[11px] tabular-nums text-ink-faint">
                {totalCount} {totalCount === 1 ? "repair" : "repairs"}
              </span>
            </div>
            {help ? <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">{help}</p> : null}

            <div className="mt-1.5">
              {visibleRows.map((row, index) => (
                <CanonicalRepairRow
                  key={row?.model?.id || row?.item?.id || `${section.key}-${index}`}
                  item={row.item}
                  model={row.model}
                  renderDetails={() => renderRow(row, index)}
                />
              ))}
            </div>

            {hiddenCount > 0 ? (
              <button
                type="button"
                onClick={() => setShowAllFixFirst(true)}
                className="mt-3 text-[13px] font-medium text-ink-muted underline decoration-hairline underline-offset-4 transition-colors hover:text-ink hover:no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                View {hiddenCount} more Fix first {hiddenCount === 1 ? "repair" : "repairs"}
              </button>
            ) : section.key === "fix_first" && showAllFixFirst && hasFixFirstOverflow ? (
              <button
                type="button"
                onClick={() => setShowAllFixFirst(false)}
                className="mt-3 text-[13px] font-medium text-ink-muted underline decoration-hairline underline-offset-4 transition-colors hover:text-ink hover:no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                Show fewer Fix first repairs
              </button>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
