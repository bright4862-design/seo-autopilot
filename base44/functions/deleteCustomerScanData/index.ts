import { createClientFromRequest } from "npm:@base44/sdk@0.8.41";

const KEEP_NEWEST = 3;
const MAX_HISTORY = 100;
const TERMINAL_STATUSES = new Set(["complete", "limited", "failed", "cancelled"]);
const ACTIVE_STATUSES = new Set(["queued", "crawling", "reviewing"]);

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
      const scans = await entities.ScanRun.filter(
        { project_id: projectId, owner_user_id: cleanId(user.id) },
        "-created_date",
        MAX_HISTORY,
      ).catch(() => []);
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

  const fixLists = await entities.FixList.filter({ scan_run_id: scanId }, "-created_date", 20).catch(() => []);
  for (const fixList of fixLists || []) {
    if (cleanId(fixList?.owner_user_id) !== cleanId(userId) || cleanId(fixList?.project_id) !== cleanId(projectId)) continue;
    const items = await entities.FixItem.filter({ fix_list_id: cleanId(fixList.id) }, "-created_date", 200).catch(() => []);
    for (const item of items || []) {
      if (
        cleanId(item?.owner_user_id) === cleanId(userId)
        && cleanId(item?.project_id) === cleanId(projectId)
        && cleanId(item?.scan_run_id) === cleanId(scanId)
        && item?.id
      ) {
        await entities.FixItem.delete(item.id);
      }
    }
    if (fixList?.id) await entities.FixList.delete(fixList.id);
  }

  // Defensive cleanup for any authority row whose list relation was lost but
  // whose scan/project/owner identity is still exact.
  const remainingItems = await entities.FixItem.filter({ scan_run_id: scanId }, "-created_date", 200).catch(() => []);
  for (const item of remainingItems || []) {
    if (
      cleanId(item?.owner_user_id) === cleanId(userId)
      && cleanId(item?.project_id) === cleanId(projectId)
      && item?.id
    ) {
      await entities.FixItem.delete(item.id);
    }
  }

  await entities.ScanRun.delete(scanId);
  return true;
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
