export const REPAIR_DELTA_PRESENTATION_VERSION = "repair_delta_presentation_v1_stable_identity_only";

/**
 * Compare two scans' persisted repairs into fixed / introduced / persisting.
 *
 * `scanHistoryLineagePresentation` deliberately stops at the lineage label and
 * sets `comparisonClaimAllowed: false`, because a label alone cannot support a
 * claim about what changed. This is the pass that earns that claim, and it
 * earns it only where the server said it could.
 *
 * The server builds a cross-scan `repair_fingerprint` and marks it
 * `repair_identity_stable` only when the repair carries a rule, an explicit
 * implementation surface AND an explicit remediation family. A provisional
 * fingerprint is explicitly "not eligible for automatic verified_fixed", so
 * unstable rows are counted here and never claimed. A repair that merely
 * resembles another by rule and page family is not the same repair.
 *
 * Absence is also not proof on its own: a repair missing from the newer scan
 * was only really fixed if the newer scan actually looked. A scan that did not
 * reach an authoritative, complete result cannot retire anything, so the whole
 * comparison is withheld rather than reported with a caveat no one reads.
 */

function clean(value = "") {
  return String(value || "").trim();
}

function stableFingerprint(item) {
  if (!item || item.repair_identity_stable !== true) return "";
  return clean(item.repair_fingerprint || item.repairFingerprint);
}

function repairsOf(scan) {
  if (!scan) return [];
  const rows = scan.canonical_repairs || scan.canonicalRepairs || scan.fix_items || scan.fixItems;
  return Array.isArray(rows) ? rows.filter((row) => row && typeof row === "object") : [];
}

/**
 * A scan may only retire a repair if it genuinely completed and its result is
 * the authoritative one. `limited`, failed, and in-flight scans are excluded:
 * they can be missing a repair because they never got far enough to see it.
 */
function isAuthoritative(scan) {
  if (!scan) return false;
  if (clean(scan.status) !== "complete") return false;
  const snapshotComplete =
    scan.repair_snapshot_contract_complete === true || scan.repairSnapshotContractComplete === true;
  return snapshotComplete && repairsOf(scan).length >= 0;
}

function indexByStableFingerprint(rows) {
  const index = new Map();
  let unstable = 0;
  for (const row of rows) {
    const fingerprint = stableFingerprint(row);
    if (!fingerprint) {
      unstable += 1;
      continue;
    }
    if (!index.has(fingerprint)) index.set(fingerprint, row);
  }
  return { index, unstable };
}

/**
 * @returns null when no honest comparison is possible, otherwise the delta.
 */
export function repairDeltaPresentation({ current, previous } = {}) {
  const parentScanId = clean(
    current?.rescan_of_scan_id || current?.rescanOfScanId || current?.previous_scan_id || current?.previousScanId,
  );
  if (!parentScanId) return null;

  const previousId = clean(previous?.id || previous?.scan_id || previous?.scanId);
  // Comparing against a scan that is not the declared parent would attribute
  // another site's or another attempt's repairs to this lineage.
  if (!previousId || previousId !== parentScanId) return null;

  if (!isAuthoritative(current) || !isAuthoritative(previous)) return null;

  const currentRows = indexByStableFingerprint(repairsOf(current));
  const previousRows = indexByStableFingerprint(repairsOf(previous));

  const fixed = [];
  for (const [fingerprint, row] of previousRows.index) {
    if (!currentRows.index.has(fingerprint)) fixed.push(row);
  }
  const introduced = [];
  const persisting = [];
  for (const [fingerprint, row] of currentRows.index) {
    (previousRows.index.has(fingerprint) ? persisting : introduced).push(row);
  }

  const unverifiedCount = currentRows.unstable + previousRows.unstable;

  return {
    version: REPAIR_DELTA_PRESENTATION_VERSION,
    state: "verified_repair_delta",
    comparedAgainstScanId: parentScanId,
    fixed,
    introduced,
    persisting,
    fixedCount: fixed.length,
    introducedCount: introduced.length,
    persistingCount: persisting.length,
    // Rows whose identity the server marked provisional. Surfaced as a count so
    // the customer can see the comparison is partial, never folded into a claim.
    unverifiedCount,
    comparisonClaimAllowed: true,
  };
}
