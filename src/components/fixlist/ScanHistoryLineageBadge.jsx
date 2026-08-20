import React, { useMemo } from "react";

import { scanHistoryLineagePresentation } from "@/lib/scanHistoryPresentation";

/**
 * Presentation-only history cue. It can say only that this saved scan has an
 * explicit durable parent scan; it makes no comparison, improvement, or repair
 * verification claim.
 */
export default function ScanHistoryLineageBadge({ scan = {} }) {
  const model = useMemo(() => scanHistoryLineagePresentation(scan), [scan]);
  if (!model) return null;

  return (
    <span
      className="inline-flex items-center rounded-full border border-hairline-soft px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em] text-ink-faint"
      title="This scan explicitly references an earlier saved scan."
    >
      {model.label}
    </span>
  );
}
