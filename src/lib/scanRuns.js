// Durable metadata for the synchronous Standard-150 scan path. A ScanRun must
// exist before scanner network work begins. This does not provide a production
// queue or asynchronous recovery; Premium remains blocked on that coordinator.

import { base44 } from "@/api/base44Client";
import { getActiveProject } from "@/lib/activeProject";
import { clearCustomerAuthBoundary } from "@/lib/customerBrowserCache";
import {
  buildFixItemFields,
  buildFixListFields,
  buildScanRunFields,
  deriveTerminalStatus,
  getFixRecommendations,
} from "@/lib/scanRunModel";
import {
  ACTIVE_SCAN_RUN_STATUSES,
  STANDARD_ACTIVE_SCAN_TTL_MS,
  STANDARD_ORPHAN_RECOVERY_TTL_MS,
  ScanRunConflictError,
  buildScanRequestIdentity,
  buildStaleScanRetryFields,
  isStaleActiveScanRun,
  normalizeScanMode,
  normalizeScanTarget,
  normalizedScanDomain,
  resolveScanRunReplay,
  scanReleaseIdentity,
} from "@/lib/scanRunIdentity";

// Terminal states that already carry persisted evidence. Recovery and
// gateway-observed failures must never overwrite these.
const PROTECTED_SCAN_STATUSES = new Set(["complete", "limited"]);
const MAX_FIX_ITEMS = 100;
const MAX_REPLAY_CANDIDATES = 50;
const pendingBeginsByRequest = new Map();
const pendingBeginsByTarget = new Map();

async function currentOwner() {
  const user = await base44.auth.me();
  if (!user?.id) throw new Error("Sign in before starting a durable scan.");
  return { owner_user_id: user.id };
}

function scanRunHandle(run, { replayed = false, replayReason = "", retried = false } = {}) {
  if (!run?.id) throw new Error("Durable ScanRun creation did not return an entity id.");
  const projectId = String(run.project_id || "").trim();
  if (!projectId) throw new Error("Durable ScanRun is missing its website project identity.");
  return {
    id: run.id,
    scan_id: run.id,
    request_id: run.request_id || "",
    idempotency_key: run.idempotency_key || run.request_id || "",
    request_fingerprint: run.request_fingerprint || "",
    project_id: projectId,
    owner_user_id: run.owner_user_id || "",
    website_url: run.website_url || "",
    submitted_url: run.submitted_url || run.website_url || "",
    normalized_domain: run.normalized_domain || normalizedScanDomain(run.website_url),
    // Legacy quick/basic/deep records stay readable as their original mode;
    // only the retired "advanced" alias resolves to the canonical customer mode.
    scan_mode: normalizeScanMode(run.scan_mode),
    previous_scan_id: run.previous_scan_id || "",
    fix_list_id: run.fix_list_id || "",
    status: run.status || "queued",
    replayed,
    replay_reason: replayReason,
    retried,
  };
}

async function resolveProjectId(projectId) {
  const explicitProjectId = String(projectId || "").trim();
  if (explicitProjectId) return explicitProjectId;
  try {
    const { project } = await getActiveProject();
    const activeProjectId = String(project?.id || "").trim();
    if (activeProjectId) return activeProjectId;
  } catch {
    // Fall through to the fail-closed error below.
  }
  throw new Error("A website project is required before starting a durable scan.");
}

// A run whose browser died mid-scan never reaches a terminal state on its own.
// These rows are failed truthfully -- no result is fabricated and no scanner
// identity is backfilled -- so the request key is free for a clean retry.
const STALE_RUN_STATUS_DETAIL =
  "This scan stopped before it finished and no results were saved. You can run it again.";

async function terminalizeStaleScanRuns(runs = [], { ttlMs = STANDARD_ACTIVE_SCAN_TTL_MS } = {}) {
  const completedAt = new Date().toISOString();
  const uniqueRuns = [...new Map(
    (runs || [])
      .filter((run) => run?.id)
      // Defensive: a run that already reached complete/limited carries persisted
      // evidence and must never be overwritten by recovery.
      .filter((run) => !PROTECTED_SCAN_STATUSES.has(String(run.status || "").toLowerCase()))
      .map((run) => [run.id, run]),
  ).values()];
  await Promise.allSettled(uniqueRuns.map((run) =>
    base44.entities.ScanRun.update(run.id, {
      status: "failed",
      status_detail: STALE_RUN_STATUS_DETAIL,
      error_code: "orphaned_no_terminal_state",
      error_message: `Standard scan exceeded the ${Math.round(ttlMs / 60000)}-minute active recovery window without reaching a terminal state.`,
      completed_at: completedAt,
      release_gate_eligible: false,
    }),
  ));
  return uniqueRuns.map((run) => run.id);
}

// A scan the browser abandoned mid-flight -- the customer signed out, switched
// account or project, or the request was superseded. The row is closed
// truthfully as cancelled: no result is fabricated, no scanner identity is
// backfilled, and because the allowance is only recorded after a durable
// success, a cancelled attempt never consumes it.
const CANCELLED_RUN_STATUS_DETAIL =
  "This scan was stopped before it finished, so no results were saved. You can run it again.";

export async function cancelScanRun(handle, error) {
  if (!handle?.id) return null;
  try {
    const cancelledFields = {
      status: "cancelled",
      status_detail: CANCELLED_RUN_STATUS_DETAIL,
      cancelled_reason: String(error?.code || error?.name || "customer_session_changed").slice(0, 120),
      completed_at: new Date().toISOString(),
      release_gate_eligible: false,
    };
    const updatedRun = await base44.entities.ScanRun.update(handle.id, cancelledFields);
    return {
      requestId: handle.request_id || "",
      scanId: handle.id,
      scanRun: { id: handle.id, ...cancelledFields, ...(updatedRun || {}) },
    };
  } catch (cancelError) {
    // An expired session cannot write its own terminal state. recoverOrphanedScanRuns
    // is the backstop that closes the row on the next authenticated page load.
    console.warn("Durable scan history: could not mark ScanRun cancelled.", cancelError);
    return null;
  }
}

// Closes rows that are still "active" but can no longer be finished by anyone.
// This runs when a customer opens the scan form or a result route -- not only on
// the next submission -- so an abandoned run cannot present a permanent "still
// running" screen. Only rows past the orphan threshold are touched, so a live
// scan in another tab is never interrupted.
export async function recoverOrphanedScanRuns({ projectId = "", now = Date.now() } = {}) {
  try {
    const owner = await currentOwner();
    const scope = String(projectId || "").trim();
    const candidates = await base44.entities.ScanRun.filter(
      { ...(scope ? { project_id: scope } : {}), ...owner },
      "-queued_at",
      MAX_REPLAY_CANDIDATES,
    );
    const orphans = (candidates || []).filter((run) =>
      ACTIVE_SCAN_RUN_STATUSES.has(String(run?.status || ""))
      && isStaleActiveScanRun(run, { now, activeTtlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS }),
    );
    if (orphans.length === 0) return [];
    return await terminalizeStaleScanRuns(orphans, { ttlMs: STANDARD_ORPHAN_RECOVERY_TTL_MS });
  } catch (error) {
    clearCustomerAuthBoundary(error);
    console.warn("Durable scan history: could not recover orphaned ScanRuns.", error);
    return [];
  }
}

async function restartStaleRequestRun(run, identity) {
  if (!run?.id) throw new Error("The expired Standard scan is missing its durable identity.");
  const retryFields = buildStaleScanRetryFields(run, identity);
  // This update must succeed before any scanner network work resumes. Reusing
  // the same entity avoids deliberately creating two rows for one request key.
  const restarted = await base44.entities.ScanRun.update(run.id, retryFields);
  return scanRunHandle(
    { ...run, ...retryFields, ...(restarted || {}), id: run.id },
    { replayed: false, replayReason: "stale_request_retry", retried: true },
  );
}

async function beginPersistedScanRun({ projectId, submittedUrl, pathPrefix, scanSource, owner, identity }) {
  if (!String(projectId || "").trim()) {
    throw new Error("A website project is required before persisting a ScanRun.");
  }
  const [requestRuns, activeRuns] = await Promise.all([
    base44.entities.ScanRun.filter(
      { request_id: identity.request_id, ...owner },
      "-queued_at",
      MAX_REPLAY_CANDIDATES,
    ),
    base44.entities.ScanRun.filter(
      { project_id: projectId, normalized_domain: identity.normalized_domain, ...owner },
      "-queued_at",
      MAX_REPLAY_CANDIDATES,
    ),
  ]);
  const replay = resolveScanRunReplay({ requestRuns, activeRuns, identity });
  if (replay.action === "retry_same_run") {
    return restartStaleRequestRun(replay.run, identity);
  }
  if (replay.staleRuns?.length) await terminalizeStaleScanRuns(replay.staleRuns);
  if (replay.action === "reuse") {
    return scanRunHandle(replay.run, { replayed: true, replayReason: replay.reason });
  }

  let previousScanId = "";
  try {
    const previous = await base44.entities.ScanRun.filter(
      { project_id: projectId, ...owner },
      "-completed_at",
      20,
    );
    previousScanId = (previous || []).find((run) => ["complete", "limited"].includes(run.status))?.id || "";
  } catch {
    // Lineage is optional; identity persistence is not.
  }

  const queuedAt = new Date().toISOString();
  const created = await base44.entities.ScanRun.create({
    request_id: identity.request_id,
    idempotency_key: identity.idempotency_key,
    request_fingerprint: identity.request_fingerprint,
    project_id: projectId,
    website_url: identity.normalized_target,
    submitted_url: String(submittedUrl || identity.normalized_target),
    final_url: "",
    normalized_domain: identity.normalized_domain,
    path_prefix: pathPrefix || "",
    scan_mode: identity.scan_mode,
    scan_source: scanSource || "scan_website_page",
    status: "queued",
    previous_scan_id: previousScanId,
    respect_robots_txt: true,
    queued_at: queuedAt,
    ...owner,
  });

  try {
    const startedAt = new Date().toISOString();
    const started = await base44.entities.ScanRun.update(created.id, {
      scan_id: created.id,
      status: "crawling",
      started_at: startedAt,
    });
    return scanRunHandle({ ...created, ...(started || {}), id: created.id, scan_id: created.id });
  } catch (error) {
    error.scan_id = created.id;
    error.request_id = identity.request_id;
    throw error;
  }
}

// Starts durable tracking and coalesces same-runtime races. Restarting an
// expired request reuses its durable row, but Base44 must still enforce an
// owner/request_id transaction or lease before cross-browser/process
// exact-once can be claimed; this client-side map is not that guarantee.
export async function beginScanRun({
  projectId,
  websiteUrl,
  submittedUrl,
  pathPrefix,
  scanMode,
  scanSource,
  requestId,
  idempotencyKey,
}) {
  const owner = await currentOwner();
  const resolvedProjectId = await resolveProjectId(projectId);
  const identity = buildScanRequestIdentity({ websiteUrl, scanMode, requestId, idempotencyKey });
  const requestKey = `${owner.owner_user_id}|${identity.request_id}`;
  const targetKey = `${owner.owner_user_id}|${resolvedProjectId}|${identity.request_fingerprint}`;

  const pendingRequest = pendingBeginsByRequest.get(requestKey);
  if (pendingRequest) {
    if (pendingRequest.fingerprint !== identity.request_fingerprint) throw new ScanRunConflictError();
    return scanRunHandle(await pendingRequest.promise, { replayed: true, replayReason: "request_replay" });
  }
  const pendingTarget = pendingBeginsByTarget.get(targetKey);
  if (pendingTarget) {
    return scanRunHandle(await pendingTarget.promise, { replayed: true, replayReason: "active_target" });
  }

  const promise = beginPersistedScanRun({
    projectId: resolvedProjectId,
    submittedUrl,
    pathPrefix,
    scanSource,
    owner,
    identity,
  });
  const pendingEntry = { promise, fingerprint: identity.request_fingerprint };
  pendingBeginsByRequest.set(requestKey, pendingEntry);
  pendingBeginsByTarget.set(targetKey, pendingEntry);
  try {
    return await promise;
  } catch (error) {
    console.warn("Durable scan history: could not begin ScanRun.", error);
    throw error;
  } finally {
    if (pendingBeginsByRequest.get(requestKey) === pendingEntry) pendingBeginsByRequest.delete(requestKey);
    if (pendingBeginsByTarget.get(targetKey) === pendingEntry) pendingBeginsByTarget.delete(targetKey);
  }
}

export async function markScanRunReviewing(handle) {
  if (!handle?.id) return;
  try {
    await base44.entities.ScanRun.update(handle.id, {
      status: "reviewing",
      reviewing_at: new Date().toISOString(),
    });
  } catch (error) {
    console.warn("Durable scan history: could not mark ScanRun reviewing.", error);
  }
}

function firstFinalUrl(record = {}, fallback = "") {
  const pages = record.crawled_pages || record.pages || record.scanned_pages || [];
  const firstPage = Array.isArray(pages) ? pages[0] || {} : {};
  return normalizeScanTarget(
    record.final_url
      || record.resolved_start_url
      || firstPage.final_url
      || record.normalized_url
      || record.website_url
      || fallback,
  );
}

function durableIdentityFields(handle, record = {}) {
  const finalUrl = firstFinalUrl(record, handle?.website_url || handle?.submitted_url || "");
  return {
    request_id: handle?.request_id || record.request_id || "",
    idempotency_key: handle?.idempotency_key || record.idempotency_key || handle?.request_id || "",
    request_fingerprint: handle?.request_fingerprint || record.request_fingerprint || "",
    scan_id: handle?.id || "",
    submitted_url: handle?.submitted_url || record.submitted_url || record.website_url || "",
    final_url: finalUrl,
    normalized_domain: normalizedScanDomain(finalUrl || handle?.website_url || record.website_url),
    respect_robots_txt: true,
    ...scanReleaseIdentity(record),
  };
}

// Persists the terminal result: updates the ScanRun to complete/limited and
// saves the FixList + FixItems (with carried_over lineage from the previous run).
export async function completeScanRun(handle, mergedRecord) {
  if (!handle?.id) return null;
  try {
    const owner = { owner_user_id: handle.owner_user_id || "" };
    const fixes = getFixRecommendations(mergedRecord).slice(0, MAX_FIX_ITEMS);
    const identityFields = durableIdentityFields(handle, mergedRecord);

    let previousItems = [];
    if (handle.previous_scan_id) {
      try {
        previousItems = await base44.entities.FixItem.filter({
          scan_run_id: handle.previous_scan_id,
          ...owner,
        });
      } catch {
        previousItems = [];
      }
    }

    const [savedFixList] = await base44.entities.FixList.filter(
      { scan_run_id: handle.id, ...owner },
      "-generated_at",
      1,
    );
    const fixList = savedFixList || await base44.entities.FixList.create({
        scan_run_id: handle.id,
        project_id: handle.project_id || "",
        ...buildFixListFields(mergedRecord, fixes),
        ...owner,
      });

    if (fixes.length > 0) {
      const savedItems = await base44.entities.FixItem.filter({ fix_list_id: fixList.id, ...owner });
      const savedKeys = new Set(
        (savedItems || []).map((item) => item.fix_id || item.lineage_key).filter(Boolean),
      );
      const unsavedFixes = fixes.filter((fix) => {
        const key = fix.fix_id || fix.id;
        return !key || !savedKeys.has(key);
      });
      if (unsavedFixes.length > 0) await base44.entities.FixItem.bulkCreate(
        unsavedFixes.map((fix) => ({
          fix_list_id: fixList.id,
          scan_run_id: handle.id,
          project_id: handle.project_id || "",
          ...buildFixItemFields(fix, { scanRunId: handle.id, previousItems }),
          ...owner,
        })),
      );
    }

    const completedAt = new Date().toISOString();
    const scanRunFields = {
      ...buildScanRunFields(mergedRecord, { status: deriveTerminalStatus(mergedRecord) }),
      ...identityFields,
      fix_list_id: fixList.id,
      completed_at: completedAt,
    };
    const updatedRun = await base44.entities.ScanRun.update(handle.id, scanRunFields);
    return {
      requestId: identityFields.request_id,
      scanId: handle.id,
      fixListId: fixList.id,
      scanRun: {
        id: handle.id,
        ...scanRunFields,
        ...(updatedRun || {}),
      },
    };
  } catch (error) {
    console.warn("Durable scan history: could not save scan result.", error);
    return null;
  }
}

export async function failScanRun(handle, error) {
  if (!handle?.id) return null;
  try {
    const identityFields = durableIdentityFields(handle, error?.scan_record || error?.scanData || {});
    const failedFields = {
      status: "failed",
      error_code: error?.code || error?.name || "scan_failed",
      error_message: String(error?.message || error || "").slice(0, 500),
      ...identityFields,
      completed_at: new Date().toISOString(),
    };
    const updatedRun = await base44.entities.ScanRun.update(handle.id, failedFields);
    return {
      requestId: identityFields.request_id,
      scanId: handle.id,
      scanRun: { id: handle.id, ...failedFields, ...(updatedRun || {}) },
    };
  } catch (updateError) {
    console.warn("Durable scan history: could not mark ScanRun failed.", updateError);
    return null;
  }
}

// Scan history per website, newest first. Returns [] when unavailable.
export async function listScanRuns(projectId, limit = 20) {
  try {
    const owner = await currentOwner();
    return (
      (await base44.entities.ScanRun.filter({ project_id: projectId || "", ...owner }, "-queued_at", limit)) || []
    );
  } catch (error) {
    console.warn("Durable scan history: could not list ScanRuns.", error);
    return [];
  }
}

// Reopen a previous scan: the run plus its saved FixList and FixItems.
export async function getScanRunWithFixList(scanRunId) {
  try {
    const owner = await currentOwner();
    const run = await base44.entities.ScanRun.get(scanRunId);
    if (!run || String(run.owner_user_id || "") !== owner.owner_user_id) return null;
    const projectId = String(run.project_id || "").trim();
    if (!projectId || String(run.id || "") !== String(scanRunId || "")) return null;
    const [fixList] = run.fix_list_id
      ? [await base44.entities.FixList.get(run.fix_list_id)]
      : await base44.entities.FixList.filter({ scan_run_id: scanRunId, ...owner }, "-generated_at", 1);
    if (fixList && (
      String(fixList.owner_user_id || "") !== owner.owner_user_id
      || String(fixList.project_id || "") !== projectId
      || String(fixList.scan_run_id || "") !== String(run.id || "")
    )) return null;
    const fixItems = fixList
      ? await base44.entities.FixItem.filter({ fix_list_id: fixList.id, ...owner })
      : [];
    if ((fixItems || []).some((item) => (
      String(item.owner_user_id || "") !== owner.owner_user_id
      || String(item.project_id || "") !== projectId
      || String(item.scan_run_id || "") !== String(run.id || "")
      || String(item.fix_list_id || "") !== String(fixList?.id || "")
    ))) return null;
    return {
      request_id: run.request_id || "",
      scan_id: run.id,
      fix_list_id: fixList?.id || run.fix_list_id || "",
      run: { ...run, scan_id: run.id },
      fixList: fixList || null,
      fixItems: fixItems || [],
    };
  } catch (error) {
    clearCustomerAuthBoundary(error);
    console.warn("Durable scan history: could not load ScanRun.", error);
    return null;
  }
}
