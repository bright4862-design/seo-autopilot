import assert from "node:assert/strict";
import test from "node:test";

import { buildScanRunFields, deriveTerminalStatus } from "../../src/lib/scanRunModel.js";

/**
 * Patch C part 2, item 9 - a limited row models as readable, never authoritative.
 *
 * The failure this guards against is quiet: a limited ScanRun that models as
 * release-eligible would be indistinguishable from a complete one everywhere
 * downstream, which is the whole thing the separate contract exists to prevent.
 */

function limitedRow(overrides = {}) {
  return {
    id: "scan_limited",
    status: "limited",
    scan_status: "inconclusive_insufficient_evidence",
    score_is_provisional: true,
    release_gate_eligible: false,
    scanner_version: "python_scanner_v3_bounded_request",
    advanced_scan_backend: "python_scanner_api",
    ai_review_backend: "python_review_api",
    pages_found: 3689,
    pages_crawled: 38,
    pages_retained: 38,
    result_integrity_version: "standard_limited_result_integrity_v1",
    result_integrity_proof: "e".repeat(64),
    fix_list_id: "fl_limited",
    ...overrides,
  };
}

test("a limited row stays limited", () => {
  assert.equal(deriveTerminalStatus(limitedRow()), "limited");
});

test("a limited row is never release-gate eligible", () => {
  const fields = buildScanRunFields(limitedRow());
  assert.equal(fields.release_gate_eligible, false);
});

test("a limited row carrying no authority proof cannot be inferred eligible", () => {
  /** Even if every version marker is current, limited is not complete. */
  const fields = buildScanRunFields(limitedRow(), { requireAuthorityProof: true });
  assert.equal(fields.release_gate_eligible, false);
});

test("a limited row keeps its integrity provenance", () => {
  const fields = buildScanRunFields(limitedRow());
  assert.equal(fields.result_integrity_version, "standard_limited_result_integrity_v1");
  assert.equal(fields.result_integrity_proof, "e".repeat(64));
});

test("a limited row never carries an authority proof", () => {
  const fields = buildScanRunFields(limitedRow());
  assert.ok(!fields.authority_proof, "a limited row must not model an authority proof");
});

test("an ordinary complete row is unaffected", () => {
  const complete = limitedRow({
    status: "complete",
    scan_status: "complete",
    score_is_provisional: false,
    release_gate_eligible: true,
    result_integrity_version: "",
    result_integrity_proof: "",
  });
  assert.equal(deriveTerminalStatus(complete), "complete");
  assert.equal(buildScanRunFields(complete).result_integrity_proof, "");
});
