import React, { useMemo } from "react";

import { zeroRepairPresentation } from "@/lib/zeroRepairPresentation";

/**
 * Presentation-only empty repair state.
 *
 * The component never infers audit success from an empty repair array. Positive
 * no-findings copy is rendered only when the shared presentation contract sees
 * explicit authoritative server evidence for that state.
 */
export default function ZeroRepairState({ scan = {}, repairCount = 0 }) {
  const model = useMemo(
    () => zeroRepairPresentation(scan, repairCount),
    [scan, repairCount],
  );

  if (!model) return null;

  return (
    <section className="mt-16 py-4" aria-labelledby="zero-repair-heading">
      <h2 id="zero-repair-heading" className="text-[22px] font-semibold tracking-tight text-ink">
        {model.title}
      </h2>
      <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-ink-muted">
        {model.detail}
      </p>
    </section>
  );
}
