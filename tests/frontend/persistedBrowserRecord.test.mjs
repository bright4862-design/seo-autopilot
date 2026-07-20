import assert from "node:assert/strict";
import test from "node:test";

import { mergePersistedScanRunRecord } from "../../src/lib/persistedScanRecord.js";


test("persisted coverage and authority override the capped browser preview", () => {
  const pages = Array.from({ length: 12 }, (_, index) => ({ url: `/page-${index}` }));
  const result = mergePersistedScanRunRecord(
    {
      id: "local-id",
      scan_id: "local-id",
      pages,
      pages_crawled: 150,
      pages_found: 150,
      pages_retained: 12,
      local_cache_complete: false,
      release_gate_eligible: false,
      score_is_provisional: false,
      beta_revision_fingerprint: "candidate",
    },
    {
      id: "run-id",
      pages_crawled: 150,
      pages_found: 150,
      pages_retained: 150,
      local_cache_complete: true,
      release_gate_eligible: true,
      score_is_provisional: false,
      status: "complete",
      scan_status: "complete",
      beta_revision_fingerprint: "candidate",
      fix_list_id: "fix-list-id",
    },
  );

  assert.equal(result.id, "run-id");
  assert.equal(result.scan_id, "run-id");
  assert.equal(result.scan_run_id, "run-id");
  assert.equal(result.fix_list_id, "fix-list-id");
  assert.equal(result.pages.length, 12);
  assert.equal(result.pages_retained, 150);
  assert.equal(result.local_cache_complete, true);
  assert.equal(result.release_gate_eligible, true);
});


test("an explicit persisted veto cannot be overridden by a stale local true", () => {
  const result = mergePersistedScanRunRecord(
    {
      id: "run-id",
      release_gate_eligible: true,
      local_cache_complete: true,
      score_is_provisional: false,
    },
    {
      id: "run-id",
      release_gate_eligible: false,
      local_cache_complete: false,
      score_is_provisional: true,
      status: "limited",
      scan_status: "complete_with_access_limitations",
    },
  );

  assert.equal(result.release_gate_eligible, false);
  assert.equal(result.local_cache_complete, false);
  assert.equal(result.score_is_provisional, true);
  assert.equal(result.status, "limited");
  assert.equal(result.scan_status, "complete_with_access_limitations");
});


test("missing persisted fields preserve the local record without inferring from preview length", () => {
  const result = mergePersistedScanRunRecord(
    {
      id: "local-id",
      pages: [{ url: "/" }],
      pages_crawled: 40,
      pages_found: 50,
      pages_retained: 40,
      local_cache_complete: true,
      release_gate_eligible: false,
    },
    {},
  );

  assert.equal(result.pages.length, 1);
  assert.equal(result.pages_crawled, 40);
  assert.equal(result.pages_found, 50);
  assert.equal(result.pages_retained, 40);
  assert.equal(result.local_cache_complete, true);
  assert.equal(result.release_gate_eligible, false);
});
