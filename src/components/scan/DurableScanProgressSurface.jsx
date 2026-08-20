import React, { useMemo } from "react";

import TruthfulScanProgress from "@/components/scan/TruthfulScanProgress";

/**
 * Adapter from the existing durable-completion hook shape to truthful progress.
 *
 * The hook remains the only reader/poller. This component is presentation-only
 * and deliberately does not use pagesFound or the product page cap as a
 * denominator. Leave-page behavior stays disabled unless the caller supplies
 * separate explicit proof that background execution is durable.
 */
export default function DurableScanProgressSurface({
  durableScan = {},
  targetLabel = "",
  elapsedLabel = "",
  fallbackPhase = "Starting your scan",
  longerThanUsual = false,
  backgroundExecutionProven = false,
  onOpenSavedScan,
}) {
  const scan = useMemo(() => ({
    status: String(durableScan?.status || ""),
    pages_crawled: Math.max(0, Number(durableScan?.pagesCrawled) || 0),
    durable_background_execution: backgroundExecutionProven === true,
  }), [durableScan?.status, durableScan?.pagesCrawled, backgroundExecutionProven]);

  return (
    <TruthfulScanProgress
      scan={scan}
      targetLabel={targetLabel}
      elapsedLabel={elapsedLabel}
      fallbackPhase={fallbackPhase}
      longerThanUsual={longerThanUsual}
      onOpenSavedScan={backgroundExecutionProven === true ? onOpenSavedScan : undefined}
    />
  );
}
