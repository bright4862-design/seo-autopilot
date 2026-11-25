/** Server-owned scan contracts. Browser input is deliberately not accepted. */
export const SCAN_PAGE_CAPS = Object.freeze({standard_150: 150, standard_500: 500});
export const MAX_SCAN_PAGE_CAP = 500;
export const AFFECTED_PAGE_LIST_LIMIT = 150;

export function trustedScanContract(scan = {}) {
  const hasSavedCap = scan.page_cap != null;
  const savedMode = String(scan.scan_mode || "standard_150");
  const mode = !hasSavedCap && savedMode === "advanced" ? "standard_150" : savedMode;
  const cap = SCAN_PAGE_CAPS[mode];
  if (!Number.isInteger(cap) || (hasSavedCap && scan.page_cap !== cap)
      || (mode === "standard_500" && (!hasSavedCap || scan.pipeline_mode !== "staged"))) throw new Error("scan_page_cap_invalid");
  return {scan_mode: mode, page_cap: cap, pipeline_mode: scan.pipeline_mode === "staged" ? "staged" : "monolith"};
}

export function frozenTaskScanContract(scan) {
  // Only V9 admission stores a cap. Old rows can still carry provider defaults
  // for the mode and pipeline, including an empty cap on readback.
  const { scan_mode, page_cap, pipeline_mode } = scan;
  if (page_cap == null && scan_mode !== "standard_500") return {};
  if (
    (scan_mode !== "standard_150" && scan_mode !== "standard_500")
    || page_cap !== SCAN_PAGE_CAPS[scan_mode]
    || (pipeline_mode !== "staged" && (pipeline_mode !== "monolith" || page_cap !== 150))
  ) throw new Error("scan_page_cap_invalid");
  return { scan_mode, page_cap, pipeline_mode };
}

export function readStagedScanSettings(env) {
  const cohort = env("SCAN_STAGED_OWNER_IDS");
  const mode = env("SCAN_PIPELINE_MODE");
  const scope = env("SCAN_STAGED_ROLLOUT_SCOPE");
  const enableEntitled500 = env("SCAN_STAGED_500_ENTITLED_ENABLED") === "true";
  const pipelineMode = mode === "staged" || mode === "monolith" ? mode : mode ? "invalid" : "absent";
  const ownerIds = String(cohort || "").split(",").map(value => value.trim()).filter(Boolean);
  let rolloutScope = "invalid";
  if ((!scope || scope === "off") && !enableEntitled500) rolloutScope = "off";
  if (scope === "paid" && pipelineMode === "staged" && !cohort && !env("SCAN_PIPELINE_OWNER_IDS")) {
    rolloutScope = "paid";
  }
  const entitled500Enabled = rolloutScope === "paid" && enableEntitled500;
  return {pipelineMode, cohort, ownerIds, rolloutScope, entitled500Enabled};
}

export function stagedScanOwnerEnabled(settings, ownerUserId) {
  return settings.rolloutScope === "off" && settings.pipelineMode === "staged"
    && settings.ownerIds.includes(String(ownerUserId || ""));
}

export function publishedPilotLaunchPolicy({ settings, user, expiresAt, nowSeconds = Date.now() / 1_000 }) {
  // A normal paid rollout explicitly retires the pilot with an expiry of 0.
  // In cohort mode the same value keeps every fresh V9 pilot launch closed.
  const configured = expiresAt !== undefined && !(settings.rolloutScope === "paid" && expiresAt === "0");
  const namedCustomer = user?.role === "user" && stagedScanOwnerEnabled(settings, user.id);
  const expiry = typeof expiresAt === "string" && /^[0-9]{1,12}$/.test(expiresAt) ? Number(expiresAt) : 0;
  return { configured, namedCustomer, enabled: configured && namedCustomer && expiry > nowSeconds };
}

export function hasLargeScanGrant(access) {
  return access?.has_full_access === true && access?.access_status === "active" && access?.page_cap === 500;
}

export function resolveServerScanContract({
  access, ownerUserId, verifiedAccess = false, env = () => "", settings = readStagedScanSettings(env),
} = {}) {
  const largeGrant = hasLargeScanGrant(access);
  const paid = settings.rolloutScope === "paid" && verifiedAccess === true
    && access?.has_full_access === true && access?.access_status === "active"
    && (!largeGrant || settings.entitled500Enabled)
    && (access.grant_source === "stripe_checkout" || (access.grant_source === "manual_grant" && largeGrant));
  const staged = paid || stagedScanOwnerEnabled(settings, ownerUserId);
  if (settings.rolloutScope === "invalid") throw new Error("scan_staged_rollout_configuration_invalid");
  return {
    scan_mode: staged && largeGrant ? "standard_500" : "standard_150",
    page_cap: staged && largeGrant ? 500 : 150,
    pipeline_mode: staged ? "staged" : "monolith",
    ...(paid ? {staged_rollout_scope: "paid"} : {}),
  };
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
  // Base44 can present an absent historical field as null. Keep it outside the old seal.
  return scan.page_cap == null && scan.scan_mode !== "standard_500" ? {} : trustedScanContract(scan);
}
