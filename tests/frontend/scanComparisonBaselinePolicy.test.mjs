import assert from "node:assert/strict";
import test from "node:test";

import {
  preservePersistedComparisonBaselineV1,
  selectComparisonBaselineV1,
} from "../../src/lib/scanComparisonBaselinePolicy.js";

const CURRENT = {
  owner_user_id: "owner",
  project_id: "project",
  normalized_domain: "example.com",
  requested_origin: "https://example.com",
  scope_type: "",
  requested_path_prefix: "",
  selection_cutoff_at: "2026-09-23T12:00:00Z",
};

test("creation does not require a preallocated ScanRun id", () => {
  const result = selectComparisonBaselineV1({
    current: CURRENT,
    candidates: [candidate("previous", "2026-09-23T10:00:00Z")],
  });

  assert.equal(result.previous_scan_id, "previous");
});

function candidate(scanId, sealedAt, overrides = {}) {
  return {
    scan_id: scanId,
    owner_user_id: "owner",
    project_id: "project",
    normalized_domain: "example.com",
    requested_origin: "https://example.com",
    scope_type: "",
    requested_path_prefix: "",
    status: "complete",
    authority_verified: true,
    sealed_at: sealedAt,
    ...overrides,
  };
}

test("creation selects the latest authenticated complete same-scope earlier seal", () => {
  const result = selectComparisonBaselineV1({
    current: CURRENT,
    candidates: [
      candidate("older", "2026-09-20T10:00:00Z"),
      candidate("latest-valid", "2026-09-23T10:00:00Z"),
      candidate("limited", "2026-09-23T11:00:00Z", { status: "limited" }),
      candidate("unauthenticated", "2026-09-23T11:15:00Z", { authority_verified: false }),
      candidate("foreign-origin", "2026-09-23T11:20:00Z", { requested_origin: "https://www.example.com" }),
      candidate("later-seal", "2026-09-23T13:00:00Z"),
    ],
  });

  assert.deepEqual(result, {
    version: "scan_comparison_baseline_policy_v1",
    state: "selected",
    previous_scan_id: "latest-valid",
    reason: "latest_authenticated_same_scope_complete_scan",
  });
});

test("selection is deterministic when seal timestamps tie", () => {
  const at = "2026-09-23T10:00:00Z";
  const left = selectComparisonBaselineV1({
    current: CURRENT,
    candidates: [candidate("scan-z", at), candidate("scan-a", at)],
  });
  const right = selectComparisonBaselineV1({
    current: CURRENT,
    candidates: [candidate("scan-a", at), candidate("scan-z", at)],
  });

  assert.equal(left.previous_scan_id, "scan-a");
  assert.deepEqual(left, right);
});

test("creation returns no baseline when no authenticated compatible candidate exists", () => {
  const result = selectComparisonBaselineV1({
    current: CURRENT,
    candidates: [
      candidate("limited", "2026-09-23T10:00:00Z", { status: "limited" }),
      candidate("different-path", "2026-09-23T10:30:00Z", {
        scope_type: "path_prefix",
        requested_path_prefix: "/shop",
      }),
    ],
  });

  assert.deepEqual(result, {
    version: "scan_comparison_baseline_policy_v1",
    state: "none",
    previous_scan_id: "",
    reason: "no_authenticated_same_scope_complete_scan",
  });
});

test("creation rejects every reader-ineligible identity boundary", () => {
  const result = selectComparisonBaselineV1({
    current: CURRENT,
    candidates: [
      candidate("foreign-owner", "2026-09-23T11:00:00Z", { owner_user_id: "other" }),
      candidate("foreign-project", "2026-09-23T11:00:00Z", { project_id: "other" }),
      candidate("foreign-domain", "2026-09-23T11:00:00Z", { normalized_domain: "other.example" }),
      candidate("foreign-origin", "2026-09-23T11:00:00Z", { requested_origin: "http://example.com" }),
      candidate("foreign-scope", "2026-09-23T11:00:00Z", {
        scope_type: "path_prefix",
        requested_path_prefix: "/shop",
      }),
      candidate("not-complete", "2026-09-23T11:00:00Z", { status: "limited" }),
      candidate("not-authenticated", "2026-09-23T11:00:00Z", { authority_verified: false }),
    ],
  });

  assert.equal(result.state, "none");
  assert.equal(result.previous_scan_id, "");
});

test("reload preserves the exact persisted pointer even when its row is deleted", () => {
  const result = preservePersistedComparisonBaselineV1({
    current: { ...CURRENT, previous_scan_id: "deleted-previous" },
  });

  assert.deepEqual(result, {
    version: "scan_comparison_baseline_policy_v1",
    state: "preserved",
    previous_scan_id: "deleted-previous",
    reason: "persisted_previous_scan_id",
  });
});

test("reload preserves an explicit no-baseline decision", () => {
  const result = preservePersistedComparisonBaselineV1({
    current: { ...CURRENT, previous_scan_id: "" },
  });

  assert.deepEqual(result, {
    version: "scan_comparison_baseline_policy_v1",
    state: "none",
    previous_scan_id: "",
    reason: "persisted_without_previous_scan",
  });
});

test("creation selector cannot recompute a persisted baseline", () => {
  assert.throws(
    () => selectComparisonBaselineV1({
      current: { ...CURRENT, previous_scan_id: "original" },
      candidates: [candidate("newer", "2026-09-23T11:00:00Z")],
    }),
    /already persists previous_scan_id/,
  );
});

test("reload never accepts a malformed persisted pointer", () => {
  for (const previous_scan_id of [undefined, null, 0, { id: "previous" }, " previous", "previous "]) {
    assert.throws(
      () => preservePersistedComparisonBaselineV1({ current: { ...CURRENT, previous_scan_id } }),
      /previous_scan_id/,
    );
  }
});

test("candidate input fails closed on duplicate or malformed identities", () => {
  const same = candidate("duplicate", "2026-09-23T10:00:00Z");
  assert.throws(
    () => selectComparisonBaselineV1({ current: CURRENT, candidates: [same, { ...same }] }),
    /duplicate candidate scan_id/,
  );
  assert.throws(
    () => selectComparisonBaselineV1({ current: CURRENT, candidates: [candidate(" bad", "2026-09-23T10:00:00Z")] }),
    /candidate scan_id/,
  );
});

test("creation descriptors reject unknown fields and non-canonical timestamps", () => {
  assert.throws(
    () => selectComparisonBaselineV1({ current: { ...CURRENT, raw_row: true }, candidates: [] }),
    /versioned descriptor fields/,
  );
  assert.throws(
    () => selectComparisonBaselineV1({
      current: { ...CURRENT, selection_cutoff_at: "2026-09-23 12:00:00Z" },
      candidates: [],
    }),
    /UTC RFC3339 timestamp/,
  );
  assert.throws(
    () => selectComparisonBaselineV1({
      current: CURRENT,
      candidates: [{ ...candidate("previous", "2026-09-23T10:00:00Z"), raw_row: true }],
    }),
    /versioned descriptor fields/,
  );
  assert.throws(
    () => selectComparisonBaselineV1({
      current: CURRENT,
      candidates: [candidate("sub-millisecond", "2026-09-23T10:00:00.0001Z")],
    }),
    /UTC RFC3339 timestamp/,
  );
  assert.throws(
    () => selectComparisonBaselineV1({
      current: CURRENT,
      candidates: [candidate("impossible-date", "2026-09-31T10:00:00Z")],
    }),
    /real UTC RFC3339 timestamp/,
  );
});

test("a seal at or after the creation cutoff is not a predecessor", () => {
  const result = selectComparisonBaselineV1({
    current: CURRENT,
    candidates: [
      candidate("same-time", "2026-09-23T12:00:00Z"),
      candidate("future", "2026-09-23T12:00:00.001Z"),
    ],
  });

  assert.equal(result.state, "none");
  assert.equal(result.previous_scan_id, "");
});
