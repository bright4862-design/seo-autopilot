import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import {
  buildScanHistoryProjection,
  recordOwnedByUser,
} from "../../base44/functions/getCustomerScanResult/projection.js";

const resultFunction = fs.readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
const scanRuns = fs.readFileSync("src/lib/scanRuns.js", "utf8");

test("saved scan history is a strict progress-only projection", () => {
  const [row] = buildScanHistoryProjection([
    {
      id: "scan_1",
      project_id: "project_1",
      website_url: "https://example.com/path",
      normalized_domain: "example.com",
      status: "complete",
      pages_found: 184,
      pages_crawled: 150,
      queued_at: "2026-08-14T10:00:00.000Z",
      started_at: "2026-08-14T10:00:01.000Z",
      reviewing_at: "2026-08-14T10:02:00.000Z",
      completed_at: "2026-08-14T10:03:00.000Z",
      health_score: 99,
      customer_summary: "secret paid summary",
      authority_proof: "a".repeat(64),
      owner_user_id: "owner_1",
      request_id: "request_1",
      release_id: "internal_release",
      release_gate_eligible: true,
    },
  ]);

  assert.deepEqual(row, {
    id: "scan_1",
    project_id: "project_1",
    website_url: "https://example.com/path",
    normalized_domain: "example.com",
    status: "complete",
    pages_found: 184,
    pages_crawled: 150,
    queued_at: "2026-08-14T10:00:00.000Z",
    started_at: "2026-08-14T10:00:01.000Z",
    reviewing_at: "2026-08-14T10:02:00.000Z",
    completed_at: "2026-08-14T10:03:00.000Z",
  });
});

test("legacy creator ownership never overrides a conflicting explicit owner", () => {
  assert.equal(recordOwnedByUser({ owner_user_id: "owner_1", created_by_id: "owner_1" }, "owner_1"), true);
  assert.equal(recordOwnedByUser({ owner_user_id: "owner_2", created_by_id: "owner_1" }, "owner_1"), false);
  assert.equal(recordOwnedByUser({ owner_user_id: "", created_by_id: "owner_1" }, "owner_1"), true);
  assert.equal(recordOwnedByUser({ created_by_id: "owner_2" }, "owner_1"), false);
});

test("the history endpoint service-reads ScanRun after an owned project check", () => {
  assert.match(resultFunction, /action\s*===\s*["']list["']/);
  assert.match(resultFunction, /loadOwnedProject\(serviceEntities\.BusinessProject/);
  assert.match(resultFunction, /serviceEntities\.ScanRun\.filter/);
  assert.match(resultFunction, /buildScanHistoryProjection/);
  assert.match(resultFunction, /Math\.min\([^\n]*3/);

  const directCallerRead = resultFunction.match(/base44\.entities\.ScanRun\.(?:get|filter)/g) || [];
  assert.deepEqual(directCallerRead, [], "customer result/history must not caller-read ScanRun");
});

test("the browser history wrapper invokes the server boundary instead of ScanRun CRUD", () => {
  const listFunction = scanRuns.match(/export async function listScanRuns[\s\S]*?\n\}/)?.[0] || "";
  assert.match(listFunction, /functions\.invoke\(["']getCustomerScanResultV2["']/);
  assert.match(listFunction, /action:\s*["']list["']/);
  assert.doesNotMatch(listFunction, /entities\.ScanRun/);
});
