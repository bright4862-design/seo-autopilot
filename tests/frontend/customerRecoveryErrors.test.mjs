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
    [{ response: { status: 409, data: { error_code: "paid_access_conflict" } } }, "access_conflict", false],
    [{ response: { status: 503, data: { error_code: "paid_access_unavailable" } } }, "unavailable", true],
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
