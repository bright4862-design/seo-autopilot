// Durable scan history persistence over the ScanRun / FixList / FixItem
// entities. Every write is best-effort: the localStorage flow stays the UI's
// source of truth until the redesign, so a failed entity write logs a warning
// and returns null instead of breaking the scan.

import { base44 } from "@/api/base44Client";
import { getActiveProject } from "@/lib/activeProject";
import {
  buildFixItemFields,
  buildFixListFields,
  buildScanRunFields,
  deriveTerminalStatus,
  getFixRecommendations,
} from "@/lib/scanRunModel";

const MAX_FIX_ITEMS = 100;

async function currentOwner() {
  const user = await base44.auth.me();
  return { owner_user_id: user?.id || "" };
}

// Starts durable tracking for a scan. Returns a handle ({ id, project_id,
// owner_user_id, previous_scan_id }) or null when persistence is unavailable.
export async function beginScanRun({ projectId, websiteUrl, pathPrefix, scanMode, scanSource }) {
  try {
    const owner = await currentOwner();
    if (!projectId) {
      try {
        const { project } = await getActiveProject();
        projectId = project?.id || "";
      } catch {
        projectId = "";
      }
    }
    let previousScanId = "";
    try {
      const previous = await base44.entities.ScanRun.filter(
        { project_id: projectId || "", ...owner },
        "-completed_at",
        1
      );
      const last = (previous || []).find((run) => ["complete", "limited"].includes(run.status));
      previousScanId = last?.id || "";
    } catch {
      // Lineage is optional; the run is still recorded without it.
    }
    const run = await base44.entities.ScanRun.create({
      project_id: projectId || "",
      website_url: websiteUrl,
      path_prefix: pathPrefix || "",
      scan_mode: scanMode === "standard_150" ? "standard_150" : "standard_150",
      scan_source: scanSource || "scan_website_page",
      status: "crawling",
      previous_scan_id: previousScanId,
      queued_at: new Date().toISOString(),
      started_at: new Date().toISOString(),
      ...owner,
    });
    return { id: run.id, project_id: projectId || "", previous_scan_id: previousScanId, ...owner };
  } catch (error) {
    console.warn("Durable scan history: could not create ScanRun.", error);
    return null;
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

// Persists the terminal result: updates the ScanRun to complete/limited and
// saves the FixList + FixItems (with carried_over lineage from the previous run).
export async function completeScanRun(handle, mergedRecord) {
  if (!handle?.id) return null;
  try {
    const owner = { owner_user_id: handle.owner_user_id || "" };
    const fixes = getFixRecommendations(mergedRecord).slice(0, MAX_FIX_ITEMS);

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

    const fixList = await base44.entities.FixList.create({
      scan_run_id: handle.id,
      project_id: handle.project_id || "",
      ...buildFixListFields(mergedRecord, fixes),
      ...owner,
    });

    if (fixes.length > 0) {
      await base44.entities.FixItem.bulkCreate(
        fixes.map((fix) => ({
          fix_list_id: fixList.id,
          scan_run_id: handle.id,
          project_id: handle.project_id || "",
          ...buildFixItemFields(fix, { scanRunId: handle.id, previousItems }),
          ...owner,
        }))
      );
    }

    const completedAt = new Date().toISOString();
    const scanRunFields = {
      ...buildScanRunFields(mergedRecord, { status: deriveTerminalStatus(mergedRecord) }),
      fix_list_id: fixList.id,
      completed_at: completedAt,
    };
    const updatedRun = await base44.entities.ScanRun.update(handle.id, scanRunFields);
    return {
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
  if (!handle?.id) return;
  try {
    await base44.entities.ScanRun.update(handle.id, {
      status: "failed",
      error_code: error?.code || error?.name || "scan_failed",
      error_message: String(error?.message || error || "").slice(0, 500),
      completed_at: new Date().toISOString(),
    });
  } catch (updateError) {
    console.warn("Durable scan history: could not mark ScanRun failed.", updateError);
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
    if (!run) return null;
    const [fixList] = run.fix_list_id
      ? [await base44.entities.FixList.get(run.fix_list_id)]
      : await base44.entities.FixList.filter({ scan_run_id: scanRunId, ...owner }, "-generated_at", 1);
    const fixItems = fixList
      ? await base44.entities.FixItem.filter({ fix_list_id: fixList.id, ...owner })
      : [];
    return { run, fixList: fixList || null, fixItems: fixItems || [] };
  } catch (error) {
    console.warn("Durable scan history: could not load ScanRun.", error);
    return null;
  }
}
