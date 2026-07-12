import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");

test("runAdvancedScan always budgets below the 105-second UI deadline", () => {
  assert.match(source, /FUNCTION_RESPONSE_BUDGET_MS = 95000/);
  assert.match(source, /quick: 55000/);
  assert.match(source, /advanced: 85000/);
  assert.doesNotMatch(source, /PYTHON_TIMEOUT_MS = 120000/);
  assert.match(source, /remainingMs = FUNCTION_RESPONSE_BUDGET_MS - \(Date\.now\(\) - functionStartedAt\)/);
  assert.match(source, /crawl_timeout_ms: Math\.min\(/);
  assert.match(source, /remainingMs - RESPONSE_RESERVE_MS/);
  assert.match(source, /not enough request time left for a safe fallback scan/);
});
