import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");

function loadRecoveryHelpers() {
  const runnable = scanRuns
    .replace(/^import[\s\S]*?;\n/gm, "")
    .replace(/^export\s+/gm, "");
  return new Function(
    `${runnable}\nreturn { classifyCustomerRecoveryError, buildCustomerSupportReference };`,
  )();
}

test("customer scan recovery has stable, allowlisted error kinds", () => {
  const { classifyCustomerRecoveryError } = loadRecoveryHelpers();
  const cases = [
    [{ response: { status: 401, data: { error_code: "unauthorized" } } }, "unauthorized", false],
    [{ response: { status: 404, data: { error_code: "scan_not_found" } } }, "not_found", false],
    [{ response: { status: 404, data: {} } }, "unavailable", true],
    [{ response: { status: 409, data: { error_code: "paid_access_conflict" } } }, "access_conflict", false],
    [{ response: { status: 503, data: { error_code: "paid_access_unavailable" } } }, "unavailable", true],
    [{ response: { status: 503, data: { error_code: "result_release_mismatch" } } }, "release_mismatch", true],
    [{ response: { status: 409, data: { error_code: "result_authority_invalid" } } }, "authority_invalid", false],
    [{ response: { status: 409, data: { error_code: "fix_items_mismatch" } } }, "authority_invalid", false],
    [{ response: { status: 409, data: { error_code: "result_not_authoritative" } } }, "not_authoritative", false],
    [{ response: { status: 500, data: { error_code: "result_load_failed" } } }, "load_failed", true],
    [new TypeError("Failed to fetch"), "unavailable", true],
  ];

  for (const [error, kind, retryable] of cases) {
    assert.deepEqual(classifyCustomerRecoveryError(error), { kind, retryable });
  }
});

test("support references are stable and do not reveal recovery identity inputs", () => {
  const { buildCustomerSupportReference } = loadRecoveryHelpers();
  const scanId = "scan_6a7f5577bd5a5dade6a1089b";
  const reference = buildCustomerSupportReference("authority_invalid", scanId);

  assert.match(reference, /^FL-[A-Z0-9]{13}$/);
  assert.equal(reference, buildCustomerSupportReference("authority_invalid", scanId));
  assert.notEqual(reference, buildCustomerSupportReference("not_found", scanId));
  assert.doesNotMatch(reference, /6a7f|scan|authority|owner|request|proof/i);
});

test("history and exact-result readers return discriminated results instead of null or empty-array failures", () => {
  const historyReader = scanRuns.match(/export async function listScanRuns[\s\S]*?\n\}/)?.[0] || "";
  const exactReader = scanRuns.match(/export async function getScanRunWithFixList[\s\S]*?\n\}/)?.[0] || "";

  assert.match(historyReader, /ok:\s*true/);
  assert.match(historyReader, /kind:\s*"loaded"/);
  assert.match(historyReader, /customerRecoveryFailure/);
  assert.doesNotMatch(historyReader, /return \[\]/);

  assert.match(exactReader, /ok:\s*true/);
  assert.match(exactReader, /kind:\s*"loaded"/);
  assert.match(exactReader, /customerRecoveryFailure/);
  assert.doesNotMatch(exactReader, /return null/);
  assert.doesNotMatch(exactReader, /request_id|owner_user_id|authority_proof/);
});

test("the customer result page renders every safe recovery state and retry action", () => {
  for (const kind of [
    "unauthorized",
    "not_found",
    "access_conflict",
    "unavailable",
    "release_mismatch",
    "authority_invalid",
    "not_authoritative",
    "load_failed",
  ]) {
    assert.match(fixList, new RegExp(`${kind}:`), `missing ${kind} copy`);
  }

  assert.match(fixList, /support_reference/);
  assert.match(fixList, /Retry loading this scan/);
  assert.match(fixList, /Retry loading saved scans/);
  assert.match(fixList, /loadedScanIdRef\.current === requestedScanId[\s\S]*?retryable/);
  assert.doesNotMatch(fixList, /owner_user_id|request_id|authority_proof/);
});

/**
 * A history read covers every saved scan in the account; a result read covers
 * one. Before this, only the button label varied by target, so an account-wide
 * failure rendered "Your saved scan has not been replaced" above a button
 * offering to "Retry loading saved scans" -- singular sentence, plural action,
 * about a record the customer had not asked for.
 *
 * FixList.jsx cannot be imported here (node --test has no JSX loader), so the
 * copy tables and the resolver are lifted out and evaluated, following the
 * loadRecoveryHelpers pattern above. The real resolver runs: asserting the
 * sentences with a regex would pass while the component still picked the wrong
 * one.
 */
function loadRecoveryCopy() {
  const parts = [
    /const CUSTOMER_RECOVERY_COPY = Object\.freeze\(\{[\s\S]*?\n\}\);/,
    /const CUSTOMER_RECOVERY_HISTORY_COPY = Object\.freeze\(\{[\s\S]*?\n\}\);/,
    /export function resolveRecoveryCopy\([\s\S]*?\n\}/,
  ].map((pattern) => {
    const found = fixList.match(pattern);
    assert.ok(found, `FixList.jsx no longer exposes ${pattern}`);
    return found[0].replace(/^export\s+/, "");
  });
  return new Function(
    `${parts.join("\n")}\nreturn { CUSTOMER_RECOVERY_COPY, CUSTOMER_RECOVERY_HISTORY_COPY, resolveRecoveryCopy };`,
  )();
}

// getCustomerScanResult's list actions raise unauthorized and result_load_failed;
// transport failures classify as unavailable. Those are the kinds a history read
// can actually reach.
const HISTORY_REACHABLE_KINDS = ["unauthorized", "unavailable", "load_failed"];

test("an account-wide history failure never describes a single saved scan", () => {
  const { resolveRecoveryCopy } = loadRecoveryCopy();
  for (const kind of HISTORY_REACHABLE_KINDS) {
    const copy = resolveRecoveryCopy(kind, "history");
    const text = `${copy.title} ${copy.detail}`;
    assert.doesNotMatch(
      text,
      /\b(this|your) (saved )?scan\b/i,
      `history copy for ${kind} still describes one scan: ${text}`,
    );
  }
});

test("history copy keeps the recovery action its single-scan counterpart uses", () => {
  const { CUSTOMER_RECOVERY_COPY, CUSTOMER_RECOVERY_HISTORY_COPY, resolveRecoveryCopy } = loadRecoveryCopy();
  for (const kind of Object.keys(CUSTOMER_RECOVERY_HISTORY_COPY)) {
    assert.equal(
      resolveRecoveryCopy(kind, "history").action,
      CUSTOMER_RECOVERY_COPY[kind].action,
      `history copy for ${kind} changes the recovery action, so the button would stop matching the sentence`,
    );
  }
});

test("a single-scan failure keeps its own wording unchanged", () => {
  const { CUSTOMER_RECOVERY_COPY, resolveRecoveryCopy } = loadRecoveryCopy();
  for (const kind of Object.keys(CUSTOMER_RECOVERY_COPY)) {
    assert.deepEqual(resolveRecoveryCopy(kind, "result"), CUSTOMER_RECOVERY_COPY[kind]);
  }
});

test("an unrecognized kind still falls back to a retryable state on both targets", () => {
  const { CUSTOMER_RECOVERY_COPY, CUSTOMER_RECOVERY_HISTORY_COPY, resolveRecoveryCopy } = loadRecoveryCopy();
  assert.deepEqual(resolveRecoveryCopy("not_a_kind", "result"), CUSTOMER_RECOVERY_COPY.load_failed);
  assert.deepEqual(resolveRecoveryCopy(undefined, "history"), CUSTOMER_RECOVERY_HISTORY_COPY.load_failed);
  // A kind with no history override must not vanish; it falls back to the
  // single-scan copy rather than rendering nothing.
  assert.deepEqual(resolveRecoveryCopy("not_authoritative", "history"), CUSTOMER_RECOVERY_COPY.not_authoritative);
});

test("no saved-scan read replaces an error without recording it first", () => {
  const fn = readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
  // The top-level handler returns a RequestProblem before reaching its own
  // console.error, so an error converted here leaves no server-side trace at
  // all -- which is how a saved-scan read failure reached a customer as a
  // support reference that could not be explained from either side.
  assert.doesNotMatch(
    fn,
    /catch\s*\{\s*throw new RequestProblem/,
    "an error replaced by a RequestProblem must be logged before it is discarded",
  );
  // Every read that converts a driver error into a customer-safe problem, not
  // just the history list: the fix_list, fix_items and access paths are the ones
  // whose copy tells the customer to contact support.
  assert.deepEqual(
    [...fn.matchAll(/logReplacedReadError\("([a-z_]+)"/g)].map((match) => match[1]).sort(),
    ["access", "fix_items", "fix_list", "list", "list_all"],
    "every saved-scan read that replaces an error must record it",
  );

  const logger = fn.match(/function logReplacedReadError\([\s\S]*?\n\}/);
  assert.ok(logger, "the replaced-error logger is missing");
  assert.doesNotMatch(
    logger[0],
    /message/,
    "bounded fields only: the replaced-error log must not record a raw driver message",
  );
});
