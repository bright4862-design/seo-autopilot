import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { durableScanStatePresentation } from "../../src/lib/durableScanStatePresentation.js";
import { scanProgressModel } from "../../src/lib/scanProgressPresentation.js";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV2/projection.js";

/**
 * A running scan says the same nine words no matter what it is doing.
 *
 * "FixList is still working" covers queued, crawling and reviewing alike, so an
 * owner watching a slow scan cannot tell whether it has started, is halfway
 * through, or is nearly done -- and the page had scanProgressModel() sitting
 * next to it the whole time, already careful about what may and may not be
 * used as a denominator.
 *
 * The rule that matters is the one that module already enforces and this must
 * not undo: `pages_found`, the Standard 150 cap, and queue length are not
 * progress totals. Discovery runs while crawling, and a site may legitimately
 * finish at 38 pages. A percentage appears only where the backend said the
 * total was final.
 */

function running(overrides = {}) {
  return { status: "crawling", pages_crawled: 38, pages_found: 3689, ...overrides };
}

test("each active phase says what is actually happening", () => {
  const phases = [
    ["queued", "Finding pages…"],
    ["crawling", "Finding and checking pages…"],
    ["reviewing", "Building your FixList…"],
  ];
  for (const [status, label] of phases) {
    const view = durableScanStatePresentation(running({ status }));
    assert.equal(view.kind, "in_progress");
    assert.equal(view.title, label, `${status} does not say what it is doing`);
  }
  const titles = new Set(phases.map(([status]) => durableScanStatePresentation(running({ status })).title));
  assert.equal(titles.size, 3, "two phases read the same");
});

test("a truthful page count is shown, and an invented denominator is not", () => {
  // 38 of 3,689 discovered is not 1% done: discovery is still running and the
  // crawl may stop at 38 legitimately. The count is real; the ratio is not.
  const view = durableScanStatePresentation(running());
  assert.equal(view.countLabel, "38 pages checked");
  assert.equal(view.percent, null, "a percentage here would be invented");
});

test("a percentage appears only once the backend calls the total final", () => {
  const locked = durableScanStatePresentation(running({
    progress_total_is_final: true,
    progress_total: 76,
  }));
  assert.equal(locked.percent, 50);
  assert.equal(locked.countLabel, "38 of 76 pages checked");

  // The three things that must never become a denominator.
  for (const invented of [
    { pages_found: 3689 },
    { queued_remaining: 112 },
    { final_page_target: 150 },
  ]) {
    const view = durableScanStatePresentation(running(invented));
    assert.equal(view.percent, null, `${JSON.stringify(invented)} was treated as progress`);
  }
});

test("leaving the page is promised only where the backend guarantees it", () => {
  const durable = durableScanStatePresentation(running({ durable_background_execution: true }));
  assert.equal(durable.canLeavePage, true);
  assert.match(durable.nextStep, /leave|come back|close/i);

  const unconfirmed = durableScanStatePresentation(running());
  assert.equal(unconfirmed.canLeavePage, false);
  assert.doesNotMatch(
    `${unconfirmed.detail} ${unconfirmed.nextStep}`,
    /safe to (leave|close)|keeps? running|in the background/i,
    "a promise the backend has not made",
  );
});

test("a slow scan is called slow only on durable evidence, never on a clock", () => {
  // A browser tab that has been open a long time proves nothing: the customer
  // may have left it open overnight on a scan that finished. The claim needs
  // the run's own timestamps and a heartbeat that is still fresh.
  const now = Date.parse("2026-09-06T12:00:00.000Z");
  const slow = durableScanStatePresentation(running({
    started_at: "2026-09-06T11:52:00.000Z",
    worker_heartbeat_at: "2026-09-06T11:59:40.000Z",
  }), { now });
  assert.match(slow.slowNote, /taking longer than usual/i);
  assert.match(slow.slowNote, /still progressing/i);

  // Fresh run: nothing to say.
  assert.equal(durableScanStatePresentation(running({
    started_at: "2026-09-06T11:59:00.000Z",
    worker_heartbeat_at: "2026-09-06T11:59:50.000Z",
  }), { now }).slowNote, "");

  // Long-running with a stale heartbeat is NOT reported as healthy -- but it is
  // not called stalled here either. Only the durable failure evidence does that.
  const stale = durableScanStatePresentation(running({
    started_at: "2026-09-06T11:40:00.000Z",
    worker_heartbeat_at: "2026-09-06T11:44:00.000Z",
  }), { now });
  assert.equal(stale.slowNote, "", "a stale heartbeat may not be described as progressing");
  assert.equal(stale.kind, "in_progress", "and it is still not a failure until the backend says so");

  // A long-running record with no heartbeat at all is the case that reads as
  // reassuring for free: the elapsed check passes and the freshness check
  // compares against NaN, which is not greater than anything. Both halves have
  // to be present for the sentence to be earned.
  assert.equal(durableScanStatePresentation(running({
    started_at: "2026-09-06T11:40:00.000Z",
  }), { now }).slowNote, "", "no heartbeat is not evidence of progress");
  assert.equal(durableScanStatePresentation(running({
    started_at: "2026-09-06T11:40:00.000Z",
    worker_heartbeat_at: "",
  }), { now }).slowNote, "");
  assert.equal(durableScanStatePresentation(running({
    started_at: "2026-09-06T11:40:00.000Z",
    worker_heartbeat_at: "not a date",
  }), { now }).slowNote, "");

  // And the mirror case: a heartbeat with no start time cannot say how long.
  assert.equal(durableScanStatePresentation(running({
    worker_heartbeat_at: "2026-09-06T11:59:40.000Z",
  }), { now }).slowNote, "");

  // No timestamps at all: no claim.
  assert.equal(durableScanStatePresentation(running(), { now }).slowNote, "");
});

test("elapsed browser time is never the source of the slow message", () => {
  const source = fs.readFileSync(new URL("../../src/lib/durableScanStatePresentation.js", import.meta.url), "utf8");
  const from = source.indexOf("function slowButHealthyNote");
  assert.ok(from > -1, "the helper must exist");
  const block = source.slice(from, source.indexOf("\n}", from));
  assert.match(block, /worker_heartbeat_at/);
  assert.match(block, /started_at/);
  assert.doesNotMatch(block, /performance\.now|Date\.now\(\)/, "the clock is passed in, not read here");
});

test("the heartbeat reaches the browser through the customer projection", () => {
  // The note above is unreachable if the field is not projected, and the page
  // would silently never show it.
  const projected = buildCustomerProjection({
    run: {
      id: "s1", scan_id: "s1", status: "crawling", pages_crawled: 38, pages_found: 3689,
      started_at: "2026-09-06T11:52:00.000Z",
      worker_heartbeat_at: "2026-09-06T11:59:40.000Z",
    },
    fixList: null,
    fixItems: [],
    fullAccess: true,
    authorityVerified: false,
  });
  assert.equal(projected.run.worker_heartbeat_at, "2026-09-06T11:59:40.000Z");

  const view = durableScanStatePresentation(projected.run, { now: Date.parse("2026-09-06T12:00:00.000Z") });
  assert.match(view.slowNote, /taking longer than usual/i);
});

test("the progress model stays the single source of these numbers", () => {
  // Two readers of the same record computing their own counts is how a page
  // ends up showing "38 pages checked" beside "12% complete".
  for (const record of [running(), running({ status: "queued", pages_crawled: 0 }), running({ progress_total_is_final: true, progress_total: 76 })]) {
    const model = scanProgressModel(record);
    const view = durableScanStatePresentation(record);
    assert.equal(view.title, model.phaseLabel);
    assert.equal(view.countLabel, model.countLabel);
    assert.equal(view.percent, model.percent);
  }
});

test("the page renders the phase, the count, and the bar it is entitled to", () => {
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  const from = page.indexOf("function RequestedScanState");
  const block = page.slice(from, page.indexOf("\nfunction ", from + 10));

  assert.match(block, /presentation\.countLabel/);
  assert.match(block, /presentation\.percent !== null/, "a bar only where a percentage is earned");
  assert.match(block, /presentation\.slowNote/);
  assert.doesNotMatch(block, /pages_found|150/, "the page must not invent its own denominator");
});
