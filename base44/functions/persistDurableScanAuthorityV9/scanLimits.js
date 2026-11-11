/** Server-owned scan contracts. Browser input is deliberately not accepted. */
export const SCAN_PAGE_CAPS = Object.freeze({standard_150: 150, standard_500: 500});
export const MAX_SCAN_PAGE_CAP = 500;
export const AFFECTED_PAGE_LIST_LIMIT = 150;

export function trustedScanContract(scan = {}) {
  const mode = String(scan.scan_mode || "standard_150");
  const cap = SCAN_PAGE_CAPS[mode];
  if (!cap || (scan.page_cap !== undefined && scan.page_cap !== cap)
      || (cap > 150 && scan.pipeline_mode !== "staged")) throw new Error("scan_page_cap_invalid");
  return {scan_mode: mode, page_cap: cap, pipeline_mode: scan.pipeline_mode === "staged" ? "staged" : "monolith"};
}

export function resolveServerScanContract({access, ownerUserId, env = () => ""} = {}) {
  const owners = String(env("SCAN_STAGED_OWNER_IDS") || "").split(",").map(v => v.trim()).filter(Boolean);
  const staged = env("SCAN_PIPELINE_MODE") === "staged" && owners.includes(String(ownerUserId || ""));
  const largeGrant = access?.has_full_access === true && access?.access_status === "active" && access?.page_cap === 500;
  return {scan_mode: staged && largeGrant ? "standard_500" : "standard_150", page_cap: staged && largeGrant ? 500 : 150, pipeline_mode: staged ? "staged" : "monolith"};
}

export function validateScanResultCap(scan, result = {}, review = {}) {
  const contract = trustedScanContract(scan);
  const count = result.pages_crawled;
  if (!Number.isInteger(count) || count < 0 || count > contract.page_cap) throw new Error("scan_page_count_invalid");
  for (const candidate of [result.scan_mode, result.canonical_mode]) {
    if (candidate !== undefined && candidate !== contract.scan_mode) throw new Error("scan_mode_mismatch");
  }
  if (result.page_cap !== undefined && result.page_cap !== contract.page_cap) throw new Error("scan_page_cap_mismatch");
  for (const value of [review?.geo_readiness?.sample_pages, review?.comparison_evidence?.observation_count]) {
    if (value !== undefined && (!Number.isInteger(value) || value < 0 || value > contract.page_cap)) throw new Error("scan_evidence_count_invalid");
  }
  return contract;
}

export function progressFields(scan, progress = {}) {
  const {page_cap} = trustedScanContract(scan);
  const crawled = progress.pages_crawled;
  const planned = progress.pages_planned;
  if (![crawled, planned].every(v => Number.isInteger(v) && v >= 0 && v <= page_cap) || crawled > planned) throw new Error("scan_progress_invalid");
  const fields = {pages_crawled: Math.max(Number(scan.pages_crawled) || 0, crawled), pages_planned: Math.max(Number(scan.pages_planned) || 0, planned), worker_heartbeat_at: new Date().toISOString()};
  if (progress.batch_committed !== undefined) {
    if (!Number.isInteger(progress.batch_committed) || progress.batch_committed < 0 || progress.batch_committed > 10000) throw new Error("scan_progress_batch_invalid");
    fields.last_committed_batch = Math.max(Number.isInteger(scan.last_committed_batch) ? scan.last_committed_batch : -1, progress.batch_committed);
  }
  return fields;
}

export function scanContractSnapshotFields(scan = {}) {
  return scan.page_cap === undefined ? {} : trustedScanContract(scan);
}
