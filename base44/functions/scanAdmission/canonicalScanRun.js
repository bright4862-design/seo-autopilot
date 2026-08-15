// Canonical ScanRun resolution for the server-owned admission path.
//
// This module is deliberately pure. It takes rows already fetched with the
// Base44 service role and decides whether the caller must create a ScanRun,
// reuse one, or fail closed. Keeping the decision separate from the fetch is
// what lets the partial-failure case be tested without a Base44 round trip.
//
// The partial failure it exists for: the server creates the ScanRun, Base44
// commits the row, and then the response is lost to a timeout or a cold start.
// The next attempt for the same request must find that single queued row and
// adopt it. Creating a second row would give one request two durable
// identities, which is the defect the whole admission design removes.

export const ACTION_CREATE = "create";
export const ACTION_REUSE = "reuse";
export const ACTION_CONFLICT = "conflict";

export const FAILURE_SCAN_CONFLICT = "admission_scan_conflict";
export const FAILURE_INVALID_IDENTITY = "admission_invalid_identity";

function text(value) {
  return String(value ?? "").trim();
}

/**
 * Narrow a candidate row set to exact owner + request matches.
 *
 * The caller's query already filters on both fields, but re-checking here
 * means a loosened or mis-specified filter upstream cannot silently widen what
 * counts as "the same request". Rows without an id are dropped: an entity with
 * no server-assigned id cannot be adopted as canonical.
 */
export function matchingScanRuns(rows, { ownerUserId, requestId }) {
  const owner = text(ownerUserId);
  const request = text(requestId);
  if (!owner || !request) return [];
  const seen = new Set();
  return (Array.isArray(rows) ? rows : []).filter((row) => {
    if (!row || typeof row !== "object") return false;
    const id = text(row.id);
    if (!id || seen.has(id)) return false;
    if (text(row.owner_user_id) !== owner) return false;
    if (text(row.request_id) !== request) return false;
    seen.add(id);
    return true;
  });
}

/**
 * Decide what to do with the rows Base44 returned for one request key.
 *
 * Zero rows  -> create exactly one, server-side.
 * One row    -> adopt it; scan_id is normalized to the entity id.
 * Many rows  -> fail closed. Two durable identities for one request is a state
 *               no automatic repair can resolve safely, because either row may
 *               already carry sealed authority.
 */
export function resolveCanonicalScanRun({ rows, ownerUserId, requestId }) {
  const owner = text(ownerUserId);
  const request = text(requestId);
  if (!owner || !request) {
    return { action: ACTION_CONFLICT, failureCode: FAILURE_INVALID_IDENTITY, scanId: "", scanRun: null };
  }

  const matches = matchingScanRuns(rows, { ownerUserId: owner, requestId: request });

  if (matches.length === 0) {
    return { action: ACTION_CREATE, failureCode: "", scanId: "", scanRun: null };
  }

  if (matches.length > 1) {
    return {
      action: ACTION_CONFLICT,
      failureCode: FAILURE_SCAN_CONFLICT,
      scanId: "",
      scanRun: null,
      conflictingScanIds: matches.map((row) => text(row.id)).sort(),
    };
  }

  const row = matches[0];
  return { action: ACTION_REUSE, failureCode: "", scanId: text(row.id), scanRun: row };
}

/**
 * Normalize a created or adopted entity to its canonical durable identity.
 *
 * Base44 assigns entity ids server-side, so `entity.id` is the only identity
 * that is guaranteed to exist and to be unique. Any `scan_id` the row happens
 * to carry is treated as advisory and overwritten -- that field is what a
 * browser used to be able to choose.
 */
export function normalizeScanIdentity(entity) {
  const id = text(entity?.id);
  if (!id) return { ok: false, failureCode: "admission_scan_id_missing", scanId: "", scanRun: null };
  return { ok: true, failureCode: "", scanId: id, scanRun: { ...entity, scan_id: id } };
}
