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
}) {
  const snapshotCount = Math.max(0, Number(presentation?.snapshotCount) || 0);
  const visibleCount = Math.max(0, Number(presentation?.visibleCount) || 0);
  const doneCount = Math.max(0, Number(markedDoneCount) || 0);

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

  if (snapshotCount === 0) {
    return <ZeroRepairState scan={scan} repairCount={0} />;
  }

  return null;
}
