import { comparisonGatewaySupportReference } from "./comparisonGateway.js";

const READER_SUPPORT_REFERENCES = new Set(["CMP-ACCESS", "CMP-CURRENT", "CMP-PREVIOUS", "CMP-SCOPE"]);
const SUPPORT_REFERENCES = new Set([
  ...READER_SUPPORT_REFERENCES, "CMP-CONFIG", "CMP-TIMEOUT", "CMP-NETWORK", "CMP-GATEWAY-AUTH", "CMP-GATEWAY-ROUTE",
  "CMP-GATEWAY-LIMIT", "CMP-GATEWAY-BUSY", "CMP-GATEWAY-ERROR", "CMP-GATEWAY-INPUT", "CMP-RESPONSE",
]);

export function validComparisonRequest(body) {
  return body && typeof body === "object" && !Array.isArray(body)
    && Object.keys(body).length === 2 && body.action === "compare"
    && typeof body.scan_id === "string" && /^[A-Za-z0-9_-]{1,160}$/.test(body.scan_id);
}

export function unavailableScanComparison(scanId, reference = "CMP-CURRENT") {
  return {
    success: true, scan_id: scanId, comparison_verified: false, comparison_status: "unavailable",
    support_reference: SUPPORT_REFERENCES.has(reference) ? reference : "CMP-CURRENT",
  };
}

function exactId(value) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,160}$/.test(value);
}

function sameScope(previous, current) {
  const left = previous.scan;
  const right = current.scan;
  const origin = (scan) => {
    const parsed = new URL(scan.requested_origin || scan.website_url);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error("invalid_origin");
    return parsed.origin;
  };
  return previous.normalized_domain === current.normalized_domain && origin(left) === origin(right)
    && (left.scope_type || "") === (right.scope_type || "")
    && (left.requested_path_prefix || "") === (right.requested_path_prefix || "");
}

/**
 * Select lineage only from service-owned rows. The existing reader supplies
 * its complete authority reconstruction + HMAC verifier, never a client receipt.
 * Optional comparison failure must not break opening the current FixList.
 */
export async function readCustomerScanComparison({
  run, user, project, access, loadRun, readVerifiedSnapshot, requestComparison,
}) {
  if (!access.ok || run.owner_user_id !== user.id || project.owner_user_id !== user.id
      || run.project_id !== project.id) return unavailableScanComparison(run.id, "CMP-ACCESS");
  if (run.status !== "complete") return unavailableScanComparison(run.id, "CMP-CURRENT");
  let stage = "CMP-CURRENT";
  try {
    const current = await readVerifiedSnapshot(run);
    if (run.previous_scan_id === undefined || run.previous_scan_id === null || run.previous_scan_id === "") {
      return { success: true, scan_id: run.id, comparison_verified: false, comparison_status: "no_previous_scan" };
    }
    stage = "CMP-PREVIOUS";
    const previousId = run.previous_scan_id;
    if (!exactId(previousId) || previousId === run.id) return unavailableScanComparison(run.id, stage);
    const previousRun = await loadRun(previousId);
    if (!previousRun || previousRun.id !== previousId || previousRun.owner_user_id !== user.id
        || previousRun.project_id !== project.id || previousRun.status !== "complete") return unavailableScanComparison(run.id, stage);
    const previous = await readVerifiedSnapshot(previousRun);
    stage = "CMP-SCOPE";
    if (!sameScope(previous.snapshot, current.snapshot)
        || !Number.isFinite(Date.parse(previous.snapshot.sealed_at))
        || !Number.isFinite(Date.parse(current.snapshot.sealed_at))
        || Date.parse(previous.snapshot.sealed_at) >= Date.parse(current.snapshot.sealed_at)) return unavailableScanComparison(run.id, stage);
    stage = "CMP-GATEWAY-ERROR";
    const presentation = await requestComparison({
      expected_owner_user_id: user.id,
      expected_project_id: project.id,
      expected_current_scan_id: run.id,
      current_previous_scan_id: previousId,
      previous_snapshot: previous.snapshot,
      previous_proof: previous.proof,
      current_snapshot: current.snapshot,
      current_proof: current.proof,
    });
    return { success: true, scan_id: run.id, comparison_verified: true, comparison_status: "ready", comparison: presentation };
  } catch (error) {
    // Prior scans may be private, unsupported, corrupt, or temporarily unreadable.
    // None of those distinctions should leak through this optional customer read.
    return unavailableScanComparison(run.id, READER_SUPPORT_REFERENCES.has(stage)
      ? stage : comparisonGatewaySupportReference(error));
  }
}
