import React, { useMemo } from "react";
import { Loader2 } from "lucide-react";

import { scanProgressModel } from "@/lib/scanProgressPresentation";

/**
 * Presentation-only active-scan status.
 *
 * The caller supplies already-read durable scan fields. This component never
 * polls, fetches, starts a scan, mutates a ScanRun, or interprets `pages_found`
 * / the product page cap as a progress denominator.
 */
export default function TruthfulScanProgress({
  scan = {},
  targetLabel = "",
  elapsedLabel = "",
  fallbackPhase = "Starting your scan",
  showSavedScanLink = false,
  onOpenSavedScan,
}) {
  const progress = useMemo(() => scanProgressModel(scan), [scan]);
  const phase = progress.status ? progress.phaseLabel : fallbackPhase;
  let detail = "";
  if (progress.status === "queued") detail = "This page updates when your scan starts.";
  else if (progress.active) detail = "This page updates as your scan runs.";
  else if (!progress.status) detail = "Keep this page open while we start your scan.";
  const canOpenSavedScan = Boolean(
    showSavedScanLink
      && progress.canLeavePage
      && typeof onOpenSavedScan === "function",
  );

  return (
    <div>
      <div className="flex items-start gap-3">
        <Loader2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-ink motion-safe:animate-spin" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <p role="status" aria-live="polite" className="text-[15px] font-medium tracking-tight">{phase}</p>
            {elapsedLabel ? (
              <span className="shrink-0 text-[12px] tabular-nums text-ink-faint">{elapsedLabel}</span>
            ) : null}
          </div>
          {targetLabel ? (
            <p className="mt-0.5 truncate text-[13px] text-ink-muted" title={targetLabel}>
              {targetLabel}
            </p>
          ) : null}
          {progress.countLabel ? (
            <p className="mt-1 text-[12px] tabular-nums text-ink-faint">
              {progress.countLabel}
            </p>
          ) : null}
          {progress.pageLimit !== null ? (
            <p className="mt-1 text-[12px] text-ink-muted">Up to {progress.pageLimit} pages in this scan</p>
          ) : null}
          {detail && <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">{detail}</p>}
          {progress.canLeavePage ? (
            <p className="mt-2 text-[12px] leading-relaxed text-ink-faint">
              You can leave this page and return to the scan from your history.
            </p>
          ) : null}
          {canOpenSavedScan ? (
            <p className="mt-3 text-[13px] leading-relaxed text-ink">
              You can{" "}
              <button
                type="button"
                onClick={onOpenSavedScan}
                className="font-semibold underline underline-offset-2"
              >
                open this saved scan
              </button>.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
