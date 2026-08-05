import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const gateway = fs.readFileSync("base44/functions/runStandard150Scan/entry.ts", "utf8");
const form = fs.readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");

test("Standard 150 preserves response time between Python, Base44, and the browser", () => {
  assert.match(gateway, /FUNCTION_RESPONSE_BUDGET_MS = 95_000/);
  assert.match(gateway, /RESPONSE_RESERVE_MS = 5_000/);
  assert.match(gateway, /UPSTREAM_RESPONSE_RESERVE_MS = 4_000/);
  assert.match(gateway, /STANDARD_CRAWL_TIMEOUT_MS = 85_000/);
  assert.match(gateway, /remainingMs = FUNCTION_RESPONSE_BUDGET_MS - \(Date\.now\(\) - startedAt\)/);
  assert.match(gateway, /upstreamTimeoutMs = remainingMs - RESPONSE_RESERVE_MS/);
  assert.match(gateway, /crawl_timeout_ms: upstreamCrawlTimeoutMs/);
  assert.match(gateway, /fetchWithTimeout\([\s\S]*upstreamTimeoutMs\)/);
  assert.doesNotMatch(gateway, /UPSTREAM_TIMEOUT_MS = 85_000/);

  assert.match(form, /crawl_timeout_ms: 90000/);
  assert.match(form, /Number\(payload\?\.crawl_timeout_ms \|\| 30000\) \+ 15000/);
});
