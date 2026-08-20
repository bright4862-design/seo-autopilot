import { buildFixListPresentation } from "./repairPresentation.js";

function repairId(item = {}) {
  return String(item?.id || item?.fix_id || item?.repair_fingerprint || "").trim();
}

/**
 * Build the exact presentation payload for the eventual FixList page migration.
 *
 * Snapshot authority always comes from the complete saved repair list. Workflow
 * filtering is passed separately as `visibleItems`, and locally marked-Done IDs
 * count only when they belong to that saved snapshot. No ranking, merging,
 * persistence, scan mutation, or verification happens here.
 */
export function buildRepairWorkSurfacePresentation({
  snapshotItems = [],
  visibleItems = [],
  doneIds = [],
  scan = {},
  initialFixFirstLimit = 3,
} = {}) {
  const snapshot = Array.isArray(snapshotItems) ? snapshotItems.filter(Boolean) : [];
  const visible = Array.isArray(visibleItems) ? visibleItems.filter(Boolean) : [];
  const snapshotIds = new Set(snapshot.map(repairId).filter(Boolean));
  const markedDoneIds = new Set(
    (Array.isArray(doneIds) ? doneIds : [])
      .map((value) => String(value || "").trim())
      .filter((value) => value && snapshotIds.has(value)),
  );

  return {
    presentation: buildFixListPresentation(snapshot, {
      visibleItems: visible,
      initialFixFirstLimit,
    }),
    scan,
    markedDoneCount: markedDoneIds.size,
  };
}
