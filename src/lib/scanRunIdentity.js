export const ACTIVE_SCAN_RUN_STATUSES = new Set(["queued", "crawling", "reviewing"]);

// The Standard scanner request deadline is under 105 seconds. Ten minutes is a
// deliberately conservative recovery window that covers scanner + review/UI
// handoff without letting abandoned active rows block later scans indefinitely.
export const STANDARD_ACTIVE_SCAN_TTL_MS = 10 * 60 * 1000;

export class ScanRunConflictError extends Error {
  constructor(message = "This scan request key was already used for a different scan.") {
    super(message);
    this.name = "ScanRunConflictError";
    this.code = "idempotency_conflict";
  }
}

export function normalizeScanMode(value) {
  return String(value || "advanced").trim().toLowerCase() || "advanced";
}

export function normalizeScanTarget(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!/^https?:$/.test(url.protocol) || !url.hostname) return "";
    url.hash = "";
    url.hostname = url.hostname.toLowerCase().replace(/\.$/, "");
    url.pathname = (url.pathname || "/").replace(/\/{2,}/g, "/");
    url.searchParams.sort();
    return url.href;
  } catch {
    return "";
  }
}

export function normalizedScanDomain(value) {
  const normalized = normalizeScanTarget(value);
  if (!normalized) return "";
  try {
    return new URL(normalized).hostname.toLowerCase().replace(/\.$/, "");
  } catch {
    return "";
  }
}

export function buildScanRequestIdentity({ websiteUrl, scanMode, requestId, idempotencyKey } = {}) {
  const normalizedTarget = normalizeScanTarget(websiteUrl);
  const normalizedMode = normalizeScanMode(scanMode);
  const stableRequestId = String(requestId || idempotencyKey || "").trim();
  const stableIdempotencyKey = String(idempotencyKey || stableRequestId).trim();
  if (!stableRequestId) throw new Error("A request ID is required before starting a durable scan.");
  if (stableRequestId !== stableIdempotencyKey) {
    throw new ScanRunConflictError("request_id and idempotency_key must match.");
  }
  if (!normalizedTarget) throw new Error("A valid website URL is required before starting a durable scan.");
  return {
    request_id: stableRequestId,
    idempotency_key: stableIdempotencyKey,
    normalized_target: normalizedTarget,
    normalized_domain: normalizedScanDomain(normalizedTarget),
    scan_mode: normalizedMode,
    request_fingerprint: `${normalizedMode}|${normalizedTarget}`,
  };
}

function storedFingerprint(run = {}) {
  return String(run.request_fingerprint || "").trim()
    || `${normalizeScanMode(run.scan_mode)}|${normalizeScanTarget(run.website_url || run.submitted_url)}`;
}

function sameTargetAndMode(run = {}, identity = {}) {
  return storedFingerprint(run) === identity.request_fingerprint;
}

function scanRunActivityTimestamp(run = {}) {
  const timestamps = [
    run.reviewing_at,
    run.started_at,
    run.queued_at,
    run.updated_date,
    run.updated_at,
    run.created_date,
    run.created_at,
  ]
    .map((value) => Date.parse(value || ""))
    .filter(Number.isFinite);
  return timestamps.length > 0 ? Math.max(...timestamps) : null;
}

export function isStaleActiveScanRun(
  run,
  { now = Date.now(), activeTtlMs = STANDARD_ACTIVE_SCAN_TTL_MS } = {},
) {
  if (!ACTIVE_SCAN_RUN_STATUSES.has(run?.status)) return false;
  const activityAt = scanRunActivityTimestamp(run);
  // Runs created by this client always carry queued_at. A legacy active row
  // with no parseable activity time cannot prove that it is still live and
  // must not become a permanent replay lock.
  if (activityAt === null) return true;
  const nowMs = now instanceof Date ? now.getTime() : Number(now);
  const ttlMs = Number(activeTtlMs);
  if (!Number.isFinite(nowMs) || !Number.isFinite(ttlMs) || ttlMs <= 0) return false;
  return nowMs - activityAt > ttlMs;
}

export function buildStaleScanRetryFields(run = {}, identity = {}, { now = Date.now() } = {}) {
  const nowMs = now instanceof Date ? now.getTime() : Number(now);
  if (!Number.isFinite(nowMs)) throw new Error("A valid retry timestamp is required.");
  const restartedAt = new Date(nowMs).toISOString();
  const attemptValue = Number(run.attempt_count);
  const currentAttempt = Number.isFinite(attemptValue)
    ? Math.max(1, Math.trunc(attemptValue))
    : 1;
  return {
    request_id: identity.request_id,
    idempotency_key: identity.idempotency_key,
    request_fingerprint: identity.request_fingerprint,
    website_url: identity.normalized_target,
    normalized_domain: identity.normalized_domain,
    scan_mode: identity.scan_mode,
    status: "crawling",
    status_detail: "Restarted after the prior Standard attempt expired.",
    attempt_count: currentAttempt + 1,
    queued_at: restartedAt,
    started_at: restartedAt,
    reviewing_at: "",
    completed_at: "",
    error_code: "",
    error_message: "",
  };
}

// Pure replay plan used by the Base44 persistence layer and focused tests.
// Candidate rows must already be owner-scoped by RLS/query filters.
export function resolveScanRunReplay({
  requestRuns = [],
  activeRuns = [],
  identity,
  now = Date.now(),
  activeTtlMs = STANDARD_ACTIVE_SCAN_TTL_MS,
} = {}) {
  const keyedRun = (requestRuns || []).find((run) => run?.request_id === identity?.request_id);
  if (keyedRun) {
    if (!sameTargetAndMode(keyedRun, identity)) throw new ScanRunConflictError();
    if (isStaleActiveScanRun(keyedRun, { now, activeTtlMs })) {
      // Keep the request key bound to this durable row. The persistence layer
      // may restart this row as a new attempt, but must not create a second row
      // with the same key merely because the first attempt expired.
      return { action: "retry_same_run", reason: "stale_request", run: keyedRun, staleRuns: [] };
    }
    return { action: "reuse", reason: "request_replay", run: keyedRun, staleRuns: [] };
  }

  const matchingActiveRuns = (activeRuns || []).filter(
    (run) => ACTIVE_SCAN_RUN_STATUSES.has(run?.status) && sameTargetAndMode(run, identity),
  );
  const staleRuns = matchingActiveRuns.filter((run) =>
    isStaleActiveScanRun(run, { now, activeTtlMs }),
  );
  const activeRun = matchingActiveRuns.find((run) =>
    !isStaleActiveScanRun(run, { now, activeTtlMs }),
  );
  if (activeRun) return { action: "reuse", reason: "active_target", run: activeRun, staleRuns };
  return {
    action: "create",
    reason: staleRuns.length > 0 ? "stale_active" : "new_request",
    run: null,
    staleRuns,
  };
}

export function createScanRequestId() {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return `scanreq_${randomUuid}`;
  return `scanreq_${Date.now()}_${Math.random().toString(36).slice(2, 14)}`;
}

export function scanReleaseIdentity(record = {}) {
  const scannerVersion = String(
    record.scanner_version || record.technical_audit_summary?.scanner_version || "",
  );
  const scannerBuildRevision = String(
    record.scanner_build_revision || record.technical_audit_summary?.scanner_build_revision || "",
  );
  const betaRevisionFingerprint = String(record.beta_revision_fingerprint || "");
  const scannerWrapperVersion = String(
    record.scanner_wrapper_version || record.wrapper_version || record.version || "",
  );
  return {
    scanner_wrapper_version: scannerWrapperVersion,
    release_id: [scannerVersion, scannerBuildRevision, betaRevisionFingerprint].filter(Boolean).join(":"),
  };
}
