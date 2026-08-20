import React, { useMemo } from "react";

import { repairWorkflowCompletionPresentation } from "@/lib/repairWorkflowPresentation";

/**
 * Presentation-only state for a saved FixList whose repairs are all locally
 * marked Done. This is intentionally not a verification/success component.
 */
export default function RepairWorkflowCompleteState({
  snapshotCount = 0,
  remainingCount = 0,
  markedDoneCount = 0,
}) {
  const model = useMemo(
    () => repairWorkflowCompletionPresentation({ snapshotCount, remainingCount, markedDoneCount }),
    [snapshotCount, remainingCount, markedDoneCount],
  );

  if (!model) return null;

  return (
    <section className="mt-12 py-4" aria-labelledby="repair-workflow-complete-heading">
      <h2 id="repair-workflow-complete-heading" className="text-[22px] font-semibold tracking-tight text-ink">
        {model.title}
      </h2>
      <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">
        {model.detail}
      </p>
    </section>
  );
}
