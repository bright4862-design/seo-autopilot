function persistedBoolean(persisted, key, fallback) {
  return typeof persisted?.[key] === "boolean" ? persisted[key] : fallback;
}

function persistedNumber(persisted, key, fallback = 0) {
  return persisted?.[key] == null ? Number(fallback || 0) : Number(persisted[key] || 0);
}

// Merge the durable ScanRun authority result into the quota-safe browser record.
// The preview arrays remain local and capped; persisted coverage and authority
// fields are copied exactly and must never be re-inferred from pages.length.
export function mergePersistedScanRunRecord(localRecord = {}, persistedScanRun = {}, fixListId = "") {
  const stableScanId = persistedScanRun?.id
    || localRecord?.scan_id
    || localRecord?.scan_run_id
    || localRecord?.id
    || "";
  const resolvedFixListId = fixListId
    || persistedScanRun?.fix_list_id
    || localRecord?.fix_list_id
    || "";

  return {
    ...localRecord,
    ...persistedScanRun,
    id: stableScanId,
    scan_id: stableScanId,
    scan_run_id: stableScanId,
    fix_list_id: resolvedFixListId,
    pages_found: persistedNumber(persistedScanRun, "pages_found", localRecord?.pages_found),
    pages_crawled: persistedNumber(persistedScanRun, "pages_crawled", localRecord?.pages_crawled),
    pages_retained: persistedNumber(persistedScanRun, "pages_retained", localRecord?.pages_retained),
    local_cache_complete: persistedBoolean(
      persistedScanRun,
      "local_cache_complete",
      localRecord?.local_cache_complete === true,
    ),
    release_gate_eligible: persistedBoolean(
      persistedScanRun,
      "release_gate_eligible",
      localRecord?.release_gate_eligible === true,
    ),
    score_is_provisional: persistedBoolean(
      persistedScanRun,
      "score_is_provisional",
      localRecord?.score_is_provisional === true,
    ),
    status: persistedScanRun?.status || localRecord?.status || "",
    scan_status: persistedScanRun?.scan_status || localRecord?.scan_status || "",
    beta_revision_fingerprint: persistedScanRun?.beta_revision_fingerprint
      || localRecord?.beta_revision_fingerprint
      || "",
  };
}
