export const RECONCILE_QUEUED_AFTER_MS = 30 * 60 * 1000;
export const RECONCILE_STARTED_AFTER_MS = 35 * 60 * 1000;
export const RECONCILE_TERMINAL_RELEASE_LOOKBACK_MS = 2 * 60 * 60 * 1000;

const TERMINAL = new Set(["complete", "limited", "failed", "cancelled"]);

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function timestampMs(value) {
  const parsed = Date.parse(text(value));
  return Number.isFinite(parsed) ? parsed : null;
}

export function reconciliationDecision(scan = {}, nowMs = Date.now()) {
  if (!text(scan?.id) || !text(scan?.admission_access_id)) {
    return { action: "skip", reason: "not_server_admitted" };
  }
  const now = Number(nowMs);
  if (!Number.isFinite(now)) return { action: "skip", reason: "invalid_now" };
  const status = text(scan?.status).toLowerCase();

  if (TERMINAL.has(status)) {
    const completed = timestampMs(scan?.completed_at || scan?.authority_sealed_at || scan?.updated_date || scan?.updated_at);
    if (completed === null || now - completed > RECONCILE_TERMINAL_RELEASE_LOOKBACK_MS) {
      return { action: "skip", reason: "terminal_outside_release_window" };
    }
    return { action: "release", reason: "terminal_release_reconciliation" };
  }

  if (status === "queued") {
    const queued = timestampMs(scan?.queued_at || scan?.created_date || scan?.created_at);
    if (queued === null) return { action: "skip", reason: "queued_timestamp_missing" };
    if (now - queued <= RECONCILE_QUEUED_AFTER_MS) return { action: "skip", reason: "queued_within_budget" };
    return {
      action: "fail",
      reason: "queued_timeout",
      error_code: "scan_queue_reconciliation_timeout",
      detail: "This scan stayed in the queue too long and was safely stopped. Please start a new scan.",
    };
  }

  if (status === "crawling" || status === "reviewing") {
    const started = timestampMs(scan?.started_at);
    if (started === null) {
      const queued = timestampMs(scan?.queued_at || scan?.created_date || scan?.created_at);
      if (queued === null || now - queued <= RECONCILE_STARTED_AFTER_MS) {
        return { action: "skip", reason: "start_timestamp_missing_within_budget" };
      }
      return {
        action: "fail",
        reason: "missing_start_timeout",
        error_code: "worker_reconciliation_timeout",
        detail: "This scan did not reach a verified worker start and was safely stopped. Please start a new scan.",
      };
    }
    if (now - started <= RECONCILE_STARTED_AFTER_MS) return { action: "skip", reason: "worker_within_budget" };
    return {
      action: "fail",
      reason: "worker_timeout",
      error_code: "worker_reconciliation_timeout",
      detail: "This scan exceeded the durable worker recovery window and was safely stopped. Please start a new scan.",
    };
  }

  return { action: "skip", reason: "status_not_reconcilable" };
}

export function uniqueRows(rows = []) {
  return [...new Map(
    (Array.isArray(rows) ? rows : [])
      .filter((row) => row && text(row.id))
      .map((row) => [text(row.id), row]),
  ).values()];
}
