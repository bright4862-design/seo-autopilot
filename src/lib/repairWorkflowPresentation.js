export const REPAIR_WORKFLOW_PRESENTATION_VERSION = "repair_workflow_presentation_v1_done_not_verified";

function count(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
}

/**
 * Present local customer workflow completion without turning it into technical
 * verification. The caller must prove that every repair in the saved snapshot
 * is actually marked Done; an empty visible list by itself is not sufficient
 * because search/filter state can also hide rows.
 */
export function repairWorkflowCompletionPresentation({
  snapshotCount = 0,
  remainingCount = 0,
  markedDoneCount = 0,
} = {}) {
  const total = count(snapshotCount);
  const remaining = count(remainingCount);
  const done = count(markedDoneCount);

  if (total <= 0 || remaining > 0 || done < total) return null;

  return {
    version: REPAIR_WORKFLOW_PRESENTATION_VERSION,
    state: "marked_done_pending_verification",
    verified: false,
    title: "Changes marked done",
    detail: "A later comparable scan is still needed before FixList can verify these repairs.",
  };
}
