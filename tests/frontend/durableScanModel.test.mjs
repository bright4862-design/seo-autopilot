import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import test from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const entitiesDir = resolve(here, "../../base44/entities");

function loadEntity(name) {
  // The .jsonc entity files in this repo contain plain JSON (no comments),
  // matching the existing entity convention, so JSON.parse is sufficient.
  const raw = readFileSync(resolve(entitiesDir, `${name}.jsonc`), "utf8");
  return JSON.parse(raw);
}

const RLS_ACTIONS = ["create", "read", "update", "delete"];

function assertOwnerScopedRls(entity) {
  assert.ok(entity.rls, `${entity.name} must define rls`);
  for (const action of RLS_ACTIONS) {
    assert.ok(entity.rls[action], `${entity.name}.rls.${action} must exist`);
  }
  // Read/update/delete must be scoped to the owner (not world-readable).
  const readClauses = JSON.stringify(entity.rls.read);
  assert.match(readClauses, /owner_user_id|created_by_id/, `${entity.name} read must be owner-scoped`);
}

function assertAdminOnlyRls(entity) {
  assert.ok(entity.rls, `${entity.name} must define rls`);
  for (const action of RLS_ACTIONS) {
    assert.equal(entity.rls[action]?.user_condition?.role, "admin", `${entity.name}.${action} must be server-only`);
  }
}

test("ScanRun encodes the roadmap status lifecycle", () => {
  const scanRun = loadEntity("ScanRun");
  assert.equal(scanRun.name, "ScanRun");
  assert.deepEqual(scanRun.properties.status.enum, [
    "queued",
    "crawling",
    "reviewing",
    "complete",
    "limited",
    "failed",
    "cancelled",
  ]);
  assert.equal(scanRun.properties.status.default, "queued");
  assert.deepEqual(scanRun.required, ["project_id", "website_url"]);
  // Existing production rows may contain an empty project_id. Enforce a
  // nonblank id in the new-write path until a measured backfill makes a
  // schema-level minLength migration safe.
  assert.equal(Object.hasOwn(scanRun.properties.project_id, "minLength"), false);
});

test("ScanRun carries retry/resume/comparison lineage fields", () => {
  const scanRun = loadEntity("ScanRun");
  for (const field of [
    "attempt_count",
    "resumable",
    "resume_token",
    "previous_scan_id",
    "rescan_of_scan_id",
    "fix_list_id",
    "score_is_provisional",
    "owner_user_id",
  ]) {
    assert.ok(scanRun.properties[field], `ScanRun missing ${field}`);
  }
  assertOwnerScopedRls(scanRun);
});

test("FixList links to a scan run and tracks priority counts", () => {
  const fixList = loadEntity("FixList");
  assert.deepEqual(fixList.required, ["scan_run_id", "project_id"]);
  for (const field of [
    "health_score",
    "total_fixes",
    "critical_count",
    "high_count",
    "medium_count",
    "low_count",
    "completed_count",
    "is_authoritative",
  ]) {
    assert.ok(fixList.properties[field], `FixList missing ${field}`);
  }
  assertAdminOnlyRls(fixList);
});

test("FixItem enums match the review-presentation contract", () => {
  const fixItem = loadEntity("FixItem");
  assert.deepEqual(fixItem.properties.page_scope.enum, ["page", "family", "cross_cutting", "sitewide"]);
  assert.deepEqual(fixItem.properties.priority.enum, ["critical", "high", "medium", "low"]);
  assert.deepEqual(fixItem.properties.user_status.enum, ["open", "in_progress", "done", "dismissed"]);
});

test("FixItem preserves finding provenance and completion tracking", () => {
  const fixItem = loadEntity("FixItem");
  for (const field of [
    "fix_id",
    "affected_pages",
    "source_pages",
    "evidence_status",
    "verification_state",
    "raw_finding",
    "completed_at",
    "completed_by_user_id",
    "first_seen_scan_run_id",
    "carried_over",
  ]) {
    assert.ok(fixItem.properties[field], `FixItem missing ${field}`);
  }
  assert.deepEqual(fixItem.required, ["fix_list_id", "scan_run_id", "project_id", "issue_title"]);
  assertAdminOnlyRls(fixItem);
});

test("all durable entities are owner-scoped and well-formed", () => {
  for (const name of ["ScanRun", "FixList", "FixItem"]) {
    const entity = loadEntity(name);
    assert.equal(entity.type, "object");
    assert.ok(entity.properties.owner_user_id, `${name} must have owner_user_id`);
    if (name === "ScanRun") assertOwnerScopedRls(entity);
    else assertAdminOnlyRls(entity);
  }
});

test("tenant inputs bind creates to the caller while sealed result rows stay server-only", () => {
  for (const name of ["BusinessProject", "ScanRun"]) {
    const entity = loadEntity(name);
    const createRules = JSON.stringify(entity.rls.create);
    assert.match(createRules, /data\.owner_user_id/, `${name} create must bind owner_user_id`);
    assert.match(createRules, /\{\{user\.id\}\}/, `${name} create must bind the caller id`);
    assert.equal(
      entity.properties.owner_user_id.rls.update.user_condition.role,
      "admin",
      `${name}.owner_user_id must be immutable to customer clients`,
    );
  }
  for (const name of ["FixList", "FixItem"]) assertAdminOnlyRls(loadEntity(name));
});
