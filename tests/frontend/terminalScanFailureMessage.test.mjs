import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { terminalScanFailureMessage } from "../../src/lib/terminalScanFailureMessage.js";

test("terminal failed scan never asks for an immediate retry or claims billing outcome", () => {
  const message = terminalScanFailureMessage("failed");
  assert.match(message, /without a verified saved result/);
  assert.match(message, /contact FixList support before starting another scan/);
  assert.doesNotMatch(message, /run it again|try again|nothing was charged|free of charge/i);
});

test("cancelled is distinct from persistence failure without implying a charge", () => {
  const message = terminalScanFailureMessage("cancelled");
  assert.match(message, /cancelled/);
  assert.match(message, /Open My scans/);
  assert.doesNotMatch(message, /contact FixList support|nothing was charged|run it again/i);
});

test("nonterminal or unknown statuses have no failure message", () => {
  for (const status of ["", "queued", "crawling", "reviewing", "complete", "limited", "unknown", null]) {
    assert.equal(terminalScanFailureMessage(status), "");
  }
});

test("scan form wires terminal failure fallback to a real dashboard action", () => {
  const source = readFileSync(new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url), "utf8");
  assert.match(source, /const message = terminalScanFailureMessage\(durableScan\.status\)/);
  assert.match(source, /setError\(message\)/);
  assert.match(source, /setErrorAction\("open_dashboard"\)/);
  assert.match(source, /errorAction === "open_dashboard"/);
  assert.doesNotMatch(source, /Nothing was charged — you can run it again/);
});
