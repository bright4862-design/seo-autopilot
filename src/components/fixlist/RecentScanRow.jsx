import React, { useState } from "react";
import { Link } from "react-router-dom";

import ScanHistoryLineageBadge from "@/components/fixlist/ScanHistoryLineageBadge";

// One saved scan in the history list. Delete is a two-step confirm so a stray
// tap can never destroy a result, and it sits outside the row's Link.
//
// The lineage badge is fail-closed: it renders only when this `scan` summary
// carries explicit durable previous/rescan IDs. The current large-page history
// summarizer does not preserve those fields yet, so this wiring changes no live
// claim until that later caller migration is made deliberately.
export default function RecentScanRow({ scan, status, occurredLabel, deleting, onDelete, child = false }) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className={`flex items-center gap-2 border-b border-hairline-soft px-2 py-1 last:border-b-0 ${child ? "bg-ink/[0.012]" : ""}`}>
      <Link
        to={`/dashboard?scan_id=${encodeURIComponent(scan.id)}`}
        className={`flex min-w-0 flex-1 items-center justify-between gap-4 rounded-lg px-3 py-3 transition-colors hover:bg-ink/[0.025] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ink ${child ? "ml-4 border-l border-hairline-soft pl-4" : ""}`}
      >
        <span className="min-w-0">
          <span className="block truncate text-[14px] font-medium text-ink">{scan.website}</span>
          {scan.scopeLabel ? <span className="mt-0.5 block truncate text-[11.5px] text-ink-muted">{scan.scopeLabel}</span> : null}
          <span className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ink-faint">
            <span className="tabular-nums">{occurredLabel}</span>
            <ScanHistoryLineageBadge scan={scan} />
          </span>
        </span>
        <span className={`shrink-0 text-[12px] font-medium ${status.active ? "text-warnink" : "text-ink-muted"}`}>
          {status.label} <span aria-hidden="true">›</span>
        </span>
      </Link>

      {status.active ? null : confirming ? (
        <span className="flex shrink-0 items-center gap-2 pr-1">
          <button
            type="button"
            disabled={deleting}
            onClick={() => onDelete(scan.project_id, scan.id)}
            className="rounded-full bg-crit px-3 py-1.5 text-[12px] font-medium text-paper transition-opacity hover:opacity-80 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
          <button
            type="button"
            disabled={deleting}
            onClick={() => setConfirming(false)}
            className="text-[12px] text-ink-muted transition-colors hover:text-ink disabled:opacity-50"
          >
            Keep
          </button>
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          aria-label={`Delete the ${scan.website} scan`}
          className="shrink-0 rounded-full px-3 py-1.5 text-[12px] font-medium text-ink-faint transition-colors hover:text-crit focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          Delete
        </button>
      )}
    </div>
  );
}
