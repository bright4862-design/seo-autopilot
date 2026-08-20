import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const rowSource = fs.readFileSync(
  new URL("../../src/components/fixlist/RecentScanRow.jsx", import.meta.url),
  "utf8",
);
const pageSource = fs.readFileSync(
  new URL("../../src/pages/FixList.jsx", import.meta.url),
  "utf8",
);

test("recent scan row is ready to render the explicit lineage badge", () => {
  assert.match(rowSource, /ScanHistoryLineageBadge/);
  assert.match(rowSource, /<ScanHistoryLineageBadge scan=\{scan\} \/>/);
});

test("current large-page summary does not yet preserve lineage so the badge remains dormant", () => {
  const summaryStart = pageSource.indexOf("function toRecentScanSummary");
  assert.ok(summaryStart >= 0, "expected toRecentScanSummary helper");
  const summaryEnd = pageSource.indexOf("\n}\n", summaryStart);
  assert.ok(summaryEnd > summaryStart, "expected end of toRecentScanSummary helper");
  const summarySource = pageSource.slice(summaryStart, summaryEnd + 2);

  assert.doesNotMatch(summarySource, /previous_scan_id|rescan_of_scan_id|previousScanId|rescanOfScanId/);
});

test("history row wiring contains no inferred trend language", () => {
  assert.doesNotMatch(rowSource, /improved|worsened|fixed|better|worse/i);
});
