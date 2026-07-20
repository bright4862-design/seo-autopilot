import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildScanRunFields } from "../../src/lib/scanRunModel.js";

const scanRunEntity = JSON.parse(readFileSync(new URL("../../base44/entities/ScanRun.jsonc", import.meta.url), "utf8"));

test("ScanRun stores crawl timing diagnostics", () => {
  assert.ok(scanRunEntity.properties.crawl_timing);
  const crawlTiming = { sitemap_budget_exhausted: true, sitemap_elapsed_ms: 1200, crawl_elapsed_ms: 23000 };
  const fields = buildScanRunFields({ crawl_timing: crawlTiming });
  assert.deepEqual(fields.crawl_timing, crawlTiming);
});
