import { createClientFromRequest } from "npm:@base44/sdk@0.8.41";

export const SCAN_HISTORY_DELETE_VERSION = "scan_history_delete_v2_drain_children";

const KEEP_NEWEST = 3;
const MAX_HISTORY = 100;
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);
const ACTIVE_STATUSES = new Set(["queued", "crawling", "reviewing"]);
const FIX_LIST_DELETE_BATCH = 20;
const FIX_ITEM_DELETE_BATCH = 200;
const MAX_DELETE_DRAIN_BATCHES = 1000;

class RequestProblem extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return problem(new RequestProblem(405, "method_not_allowed", "Use POST to manage saved scan history."));
  }

  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me().catch(() => null);
    if (!user?.id) throw new RequestProblem(401, "unauthorized", "Sign in to manage saved scans.");

    const body = unwrap(await req.json().catch(() => ({})));
    const action = cleanText(body?.action, 20).toLowerCase();
    const projectId = cleanId(body?.project_id);
    if (!projectId) throw new RequestProblem(400, "project_id_required", "Choose a website project first.");

    const entities = base44.asServiceRole.entities;
    const project = await entities.BusinessProject.get(projectId).catch(() => null);
    if (!project || cleanId(project.id) !== projectId || cleanId(project.owner_user_id) !== cleanId(user.id)) {
      throw new RequestProblem(404, "project_not_found", "This website project is not available to this account.");
    }

    if (action === "delete") {
      const scanId = cleanId(body?.scan_id);
      if (!scanId) throw new RequestProblem(400, "scan_id_required", "Choose a saved scan to delete.");
      const deleted = await deleteOwnedTerminalScan({ entities, userId: user.id, projectId, scanId });
      return Response.json({ success: true, action, deleted_scan_ids: deleted ? [scanId] : [] });
    }

    if (action === "prune") {
      const scans = await requiredRows(
        () => entities.ScanRun.filter(
          { project_id: projectId, owner_user_id: cleanId(user.id) },
          "-created_date",
          MAX_HISTORY,
        ),
        "history_scan_read_failed",
      );
      const ordered = Array.isArray(scans) ? scans : [];
      const keepIds = new Set(ordered.slice(0, KEEP_NEWEST).map((row) => cleanId(row?.id)).filter(Boolean));
      const deletedScanIds: string[] = [];
      const protectedActiveScanIds: string[] = [];

      for (const run of ordered.slice(KEEP_NEWEST)) {
        const scanId = cleanId(run?.id);
        const status = cleanText(run?.status, 30).toLowerCase();
        if (!scanId || keepIds.has(scanId)) continue;
        if (ACTIVE_STATUSES.has(status)) {
          protectedActiveScanIds.push(scanId);
          continue;
        }
        if (!TERMINAL_STATUSES.has(status)) continue;
        if (await deleteOwnedTerminalScan({ entities, userId: user.id, projectId, scanId, knownRun: run })) {
          deletedScanIds.push(scanId);
        }
      }

      return Response.json({
        success: true,
        action,
        keep_newest: KEEP_NEWEST,
        deleted_scan_ids: deletedScanIds,
        protected_active_scan_ids: protectedActiveScanIds,
      });
    }

    throw new RequestProblem(400, "action_invalid", "Choose delete or prune.");
  } catch (error) {
    return problem(error);
  }
});

async function deleteOwnedTerminalScan({ entities, userId, projectId, scanId, knownRun = null }) {
  const run = knownRun || await entities.ScanRun.get(scanId).catch(() => null);
  if (
    !run
    || cleanId(run.id) !== cleanId(scanId)
    || cleanId(run.project_id) !== cleanId(projectId)
    || cleanId(run.owner_user_id) !== cleanId(userId)
  ) {
    throw new RequestProblem(404, "scan_not_found", "This saved scan is not available to this account.");
  }

  const status = cleanText(run.status, 30).toLowerCase();
  if (ACTIVE_STATUSES.has(status)) {
    throw new RequestProblem(409, "active_scan_protected", "An active scan cannot be deleted.");
  }
  if (!TERMINAL_STATUSES.has(status)) {
    throw new RequestProblem(409, "scan_not_terminal", "Only finished scan history can be deleted.");
  }

  // Deletion must never reinterpret a storage/read failure or a capped page
  // as "no children". Drain each bounded read completely before the parent
  // ScanRun can disappear.
  await drainRows(
    () => entities.FixList.filter(
      { scan_run_id: scanId },
      "-created_date",
      FIX_LIST_DELETE_BATCH,
    ),
    FIX_LIST_DELETE_BATCH,
    "history_fix_list_read_failed",
    async (fixList) => {
      if (
        cleanId(fixList?.owner_user_id) !== cleanId(userId)
        || cleanId(fixList?.project_id) !== cleanId(projectId)
        || cleanId(fixList?.scan_run_id) !== cleanId(scanId)
        || !cleanId(fixList?.id)
      ) {
        throw new RequestProblem(
          503,
          "history_child_identity_invalid",
          "Saved scan history is temporarily unavailable.",
        );
      }

      const fixListId = cleanId(fixList.id);
      await drainRows(
        () => entities.FixItem.filter(
          { fix_list_id: fixListId },
          "-created_date",
          FIX_ITEM_DELETE_BATCH,
        ),
        FIX_ITEM_DELETE_BATCH,
        "history_fix_item_read_failed",
        async (item) => {
          requireOwnedItem(item, { userId, projectId, scanId });
          await entities.FixItem.delete(cleanId(item.id));
        },
      );
      await entities.FixList.delete(fixListId);
    },
  );

  // Defensive cleanup for authority rows whose list relation was lost but
  // whose scan/project/owner identity remains exact.
  await drainRows(
    () => entities.FixItem.filter(
      { scan_run_id: scanId },
      "-created_date",
      FIX_ITEM_DELETE_BATCH,
    ),
    FIX_ITEM_DELETE_BATCH,
    "history_orphan_item_read_failed",
    async (item) => {
      requireOwnedItem(item, { userId, projectId, scanId });
      await entities.FixItem.delete(cleanId(item.id));
    },
  );

  await entities.ScanRun.delete(scanId);
  return true;
}

function requireOwnedItem(item, { userId, projectId, scanId }) {
  if (
    cleanId(item?.owner_user_id) !== cleanId(userId)
    || cleanId(item?.project_id) !== cleanId(projectId)
    || cleanId(item?.scan_run_id) !== cleanId(scanId)
    || !cleanId(item?.id)
  ) {
    throw new RequestProblem(
      503,
      "history_child_identity_invalid",
      "Saved scan history is temporarily unavailable.",
    );
  }
}

async function drainRows(read, batchSize, readCode, deleteRow) {
  for (let batch = 0; batch < MAX_DELETE_DRAIN_BATCHES; batch += 1) {
    const rows = await requiredRows(read, readCode);
    if (rows.length === 0) return;
    for (const row of rows) {
      await deleteRow(row);
    }
    if (rows.length < batchSize) return;
  }
  throw new RequestProblem(
    503,
    "history_delete_drain_exhausted",
    "Saved scan history is temporarily unavailable.",
  );
}

async function requiredRows(read, code) {
  try {
    const rows = await read();
    if (!Array.isArray(rows)) {
      throw new Error("row_read_invalid");
    }
    return rows;
  } catch {
    throw new RequestProblem(
      503,
      code,
      "Saved scan history is temporarily unavailable.",
    );
  }
}

function unwrap(body: any) {
  return body?.data && typeof body.data === "object" ? body.data : body;
}
function cleanId(value: any) {
  const text = String(value || "").trim();
  return /^[a-zA-Z0-9_-]{6,128}$/.test(text) ? text : "";
}
function cleanText(value: any, max = 200) {
  return String(value || "").trim().slice(0, max);
}
function problem(error: any) {
  const status = Number(error?.status || 500);
  const code = cleanText(error?.code || "history_delete_failed", 80);
  const message = status >= 500 ? "Saved scan history is temporarily unavailable." : cleanText(error?.message || "The saved scan request could not be completed.", 240);
  if (status >= 500) console.error("deleteCustomerScanData failed", error instanceof Error ? error.name : "unknown_error");
  return Response.json({ success: false, error_code: code, error: message }, { status });
}
