import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  durableScanLimitationKind,
  durableScanStatePresentation,
} from "../../src/lib/durableScanStatePresentation.js";

const source = readFileSync("src/pages/FixList.jsx", "utf8");

/**
 * Records written before the scanner published structured reason codes carry
 * nothing but a sentence somebody wrote into `status_detail` or `error_code`.
 * Those rows are still in the database and still openable, so the text patterns
 * that read them are a live contract, not leftovers -- and they are the only
 * part of the classifier that cannot be checked against a producer constant.
 */
const HISTORICAL = [
  { kind: "access_limited", rows: [
    { error_code: "http_429_rate_limited" },
    { status_detail: "Cloudflare challenge returned for most requests" },
    { status_detail: "bot protection blocked the scanner" },
    { error_code: "scanner_blocked_by_origin" },
  ] },
  { kind: "worker_stalled", rows: [
    { status_detail: "heartbeat missing for 4 minutes" },
    { error_code: "run_orphaned" },
    { status_detail: "worker vanished; no_terminal state recorded" },
    { status_detail: "progress stopped" },
  ] },
  { kind: "save_failed", rows: [
    { error_code: "authority_write_failed" },
    { status_detail: "could not persist the verified result" },
    { error_code: "result_write_rejected" },
  ] },
];

test("historical free-text failures still classify without structured codes", () => {
  for (const { kind, rows } of HISTORICAL) {
    for (const row of rows) {
      assert.equal(
        durableScanLimitationKind(row),
        kind,
        `${JSON.stringify(row)} should read as ${kind}`,
      );
    }
  }
});

test("a structured code outranks whatever the free text happens to say", () => {
  // Both are present on rows written during the changeover. The structured
  // field is the producer's own verdict; the sentence is whatever was logged.
  const row = {
    status: "limited",
    evidence_quality_state: "access_limited",
    status_detail: "crawl deadline reached after 38 pages",
  };
  assert.equal(durableScanLimitationKind(row), "access_limited");
});

test("each terminal cause still reads as its own thing", () => {
  const views = HISTORICAL.map(({ rows }) => durableScanStatePresentation({ status: "failed", ...rows[0] }));
  const details = new Set(views.map((view) => view.detail));
  assert.equal(details.size, HISTORICAL.length, "two causes share one explanation");
  for (const view of views) {
    assert.ok(view.title && view.detail && view.nextStep && view.retryAdvice);
  }
});

test("a cancelled scan is not described as a fault", () => {
  const view = durableScanStatePresentation({ status: "cancelled" });
  assert.match(view.detail, /This scan was stopped before it finished/);
  assert.doesNotMatch(view.detail, /couldn't|could not|failed/i);
});

test("terminal recovery exposes the durable scan reference", () => {
  assert.match(source, /reference=\{scanRecord\.scan_id \|\| scanRecord\.id\}/);
  assert.match(source, /Scan reference:/);
});
