import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { durableScanStatePresentation } from "../../src/lib/durableScanStatePresentation.js";

const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
const recentScanRow = readFileSync("src/components/fixlist/RecentScanRow.jsx", "utf8");

test("the dashboard lists recent account-wide ScanRuns only when no exact scan is requested", () => {
  assert.doesNotMatch(fixList, /import \{ getActiveProject \} from "@\/lib\/activeProject"/);
  assert.match(fixList, /import \{ getScanRunWithFixList, listAccountScanRuns \} from "@\/lib\/scanRuns"/);
  assert.match(fixList, /if \(requestedScanId\)[\s\S]*?setRecentScans\(\[\]\)[\s\S]*?return/);
  assert.match(fixList, /await listAccountScanRuns\(/);
});

test("recent scan rows reopen only their exact encoded durable scan id", () => {
  assert.match(
    recentScanRow,
    /to=\{`\/dashboard\?scan_id=\$\{encodeURIComponent\(scan\.id\)\}`\}/,
  );
  assert.doesNotMatch(`${fixList}\n${recentScanRow}`, /latest scan|latest result|readBestScanRecord|loaded_local/);
});

test("history state stores and renders only customer-safe scan summary fields", () => {
  const projection = fixList.match(/function toRecentScanSummary\([\s\S]*?\n\}/)?.[0] || "";
  const history = fixList.match(/function RecentScansState\([\s\S]*?\n\}/)?.[0] || "";
  assert.ok(projection, "missing recent ScanRun customer projection");
  assert.ok(history, "missing recent scans state");
  for (const source of [projection, history]) {
    assert.doesNotMatch(source, /authority_proof|request_id|idempotency_key|owner_user_id|created_by_id|resume_token/);
    assert.doesNotMatch(source, /entities\.(?:FixList|FixItem)/);
  }
  assert.match(projection, /id:/);
  assert.match(projection, /website:/);
  assert.match(projection, /status:/);
  assert.match(projection, /occurredAt:/);
});

test("history copy distinguishes active, complete, failed, limited, and cancelled runs truthfully", () => {
  const statusFunction = fixList.match(/function getRecentScanStatus\([\s\S]*?\n\}/)?.[0] || "";
  assert.ok(statusFunction, "missing recent scan status formatter");
  const getRecentScanStatus = new Function(`${statusFunction}\nreturn getRecentScanStatus;`)();

  assert.deepEqual(getRecentScanStatus("queued"), { label: "Queued", active: true });
  assert.deepEqual(getRecentScanStatus("crawling"), { label: "Scanning", active: true });
  assert.deepEqual(getRecentScanStatus("reviewing"), { label: "Preparing FixList", active: true });
  assert.deepEqual(getRecentScanStatus("complete"), { label: "Completed", active: false });
  assert.deepEqual(getRecentScanStatus("failed"), { label: "Failed", active: false });
  assert.deepEqual(getRecentScanStatus("limited"), { label: "Limited", active: false });
  assert.deepEqual(getRecentScanStatus("cancelled"), { label: "Cancelled", active: false });
});

test("opening a limited run explains the evidence limitation instead of claiming no saved result", () => {
  // A limited run used to fall through to the same "no results saved" copy as
  // a run that never happened. It now resolves to a stated reason -- and the
  // reason is read from the record, so this checks two different limited runs
  // do not arrive at the same explanation.
  const blocked = durableScanStatePresentation({ status: "limited", evidence_quality_state: "access_limited" });
  const thin = durableScanStatePresentation({ status: "limited", evidence_quality_state: "insufficient_discovery" });

  for (const view of [blocked, thin]) {
    assert.notEqual(view.kind, "no_results");
    assert.doesNotMatch(view.title, /No results saved/i);
    assert.ok(view.detail.length > 0 && view.nextStep.length > 0);
  }
  assert.notEqual(blocked.kind, thin.kind);
  assert.notEqual(blocked.detail, thin.detail);

  // The page hands the whole presentation over rather than picking a title.
  assert.match(fixList, /presentation=\{durableScanStatePresentation\(scanRecord\)\}/);
});
