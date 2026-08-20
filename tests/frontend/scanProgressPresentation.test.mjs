import assert from "node:assert/strict";
import test from "node:test";

import { scanProgressModel } from "../../src/lib/scanProgressPresentation.js";

test("does not use the Standard 150 cap as a progress denominator", () => {
  const model = scanProgressModel({
    status: "crawling",
    pages_crawled: 67,
    pages_found: 5000,
    scan_mode: "standard_150",
  });

  assert.equal(model.determinate, false);
  assert.equal(model.percent, null);
  assert.equal(model.totalPages, null);
  assert.equal(model.countLabel, "67 pages checked");
});

test("does not use pages_found as a progress denominator", () => {
  const model = scanProgressModel({
    status: "crawling",
    pages_crawled: 42,
    pages_found: 84,
  });

  assert.equal(model.determinate, false);
  assert.equal(model.percent, null);
  assert.equal(model.countLabel, "42 pages checked");
});

test("uses a determinate total only when the backend explicitly locks it", () => {
  const model = scanProgressModel({
    status: "crawling",
    pages_crawled: 42,
    progress_total_locked: true,
    progress_total: 84,
  });

  assert.equal(model.determinate, true);
  assert.equal(model.totalPages, 84);
  assert.equal(model.percent, 50);
  assert.equal(model.countLabel, "42 of 84 pages checked");
});

test("completed scan may use its final checked count as a determinate total", () => {
  const model = scanProgressModel({
    status: "complete",
    pages_crawled: 79,
    pages_found: 5000,
  });

  assert.equal(model.determinate, true);
  assert.equal(model.totalPages, 79);
  assert.equal(model.percent, 100);
  assert.equal(model.countLabel, "79 of 79 pages checked");
});

test("review phase stays semantically separate from crawl completion", () => {
  const model = scanProgressModel({
    status: "reviewing",
    pages_crawled: 150,
  });

  assert.equal(model.phaseLabel, "Building your FixList…");
  assert.equal(model.determinate, false);
  assert.equal(model.countLabel, "150 pages checked");
});

test("leave-page reassurance requires explicit durable execution evidence", () => {
  assert.equal(scanProgressModel({ status: "crawling" }).canLeavePage, false);
  assert.equal(
    scanProgressModel({ status: "crawling", durable_background_execution: true }).canLeavePage,
    true,
  );
});
