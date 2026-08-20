import React from "react";

import RepairSectionList from "@/components/fixlist/RepairSectionList";
import RepairWorkflowCompleteState from "@/components/fixlist/RepairWorkflowCompleteState";
import ZeroRepairState from "@/components/fixlist/ZeroRepairState";

/**
 * Presentation-only switch for the customer repair work surface.
 *
 * The caller owns the immutable snapshot/visible-item contract and supplies an
 * already-built presentation plan. This component never ranks, filters, fetches,
 * persists, verifies, or infers that an empty list means the site is healthy.
 */
export default function RepairWorkSurface({
  presentation = {},
  renderRow,
  scan = {},
  markedDoneCount = 0,
  onClearFilters,
}) {
  const snapshotCount = Math.max(0, Number(presentation?.snapshotCount) || 0);
  const visibleCount = Math.max(0, Number(presentation?.visibleCount) || 0);
  const doneCount = Math.max(0, Number(markedDoneCount) || 0);
  const remainingCount = Math.max(0, snapshotCount - doneCount);

  if (presentation?.canonical === true && visibleCount > 0) {
    return <RepairSectionList sections={presentation.sections || []} renderRow={renderRow} />;
  }

  if (
    presentation?.canonical === true
    && snapshotCount > 0
    && visibleCount === 0
    && doneCount === snapshotCount
  ) {
    return (
      <RepairWorkflowCompleteState
        snapshotCount={snapshotCount}
        remainingCount={0}
        markedDoneCount={doneCount}
      />
    );
  }

  if (
    presentation?.canonical === true
    && snapshotCount > 0
    && visibleCount === 0
    && doneCount < snapshotCount
  ) {
    return (
      <div className="mt-12 rounded-2xl border border-hairline-soft bg-white/40 px-5 py-6">
        <h2 className="text-[20px] font-semibold tracking-tight">No repairs match this view</h2>
        <p className="mt-2 max-w-[48ch] text-[14px] leading-relaxed text-ink-muted">
          {remainingCount} {remainingCount === 1 ? "repair remains" : "repairs remain"} in your FixList.
        </p>
        {typeof onClearFilters === "function" ? (
          <button
            type="button"
            onClick={onClearFilters}
            className="mt-4 text-[13.5px] font-medium text-ink underline underline-offset-4 transition-opacity hover:opacity-70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            Clear filters
          </button>
        ) : null}
      </div>
    );
  }

  if (snapshotCount === 0) {
    return <ZeroRepairState scan={scan} repairCount={0} />;
  }

  return null;
}
