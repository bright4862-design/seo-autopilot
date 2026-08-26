import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResult/projection.js";

function run(status = "limited") {
  return {
    id: "scan-1",
    project_id: "project-1",
    website_url: "https://example.com",
    normalized_domain: "example.com",
    status,
    health_score: 72,
    health_grade: "C",
    score_is_provisional: status === "limited",
    release_gate_eligible: status === "complete",
  };
}

function fixList(authoritative = false) {
  return {
    id: "fixlist-1",
    scan_run_id: "scan-1",
    project_id: "project-1",
    website_url: "https://example.com",
    is_authoritative: authoritative,
    health_score: 72,
    health_grade: "C",
    score_is_provisional: !authoritative,
    total_fixes: 1,
  };
}

test("verified limited result explicitly declares its numeric score unavailable for customer comparison", () => {
  const projected = buildCustomerProjection({
    run: run("limited"),
    fixList: fixList(false),
    fixItems: [{ id: "item-1", fix_list_id: "fixlist-1", scan_run_id: "scan-1", project_id: "project-1" }],
    fullAccess: true,
    authorityVerified: false,
    resultIntegrityVerified: true,
  });

  assert.equal(projected.result_integrity_verified, true);
  assert.equal(projected.authority_verified, false);
  assert.equal(projected.run.health_score, 72, "sealed numeric evidence may remain available to the projection");
  assert.equal(projected.run.health_score_status, "insufficient_evidence");
});

test("authoritative result explicitly marks its score as authoritative", () => {
  const projected = buildCustomerProjection({
    run: run("complete"),
    fixList: fixList(true),
    fixItems: [],
    fullAccess: true,
    authorityVerified: true,
    resultIntegrityVerified: false,
  });

  assert.equal(projected.authority_verified, true);
  assert.equal(projected.run.health_score_status, "authoritative");
  assert.equal(projected.run.health_score, 72);
});

test("FixList browser consumes backend score status instead of treating every readable result as scored", () => {
  const source = readFileSync("src/pages/FixList.jsx", "utf8");
  const unavailable = source.match(/function isHealthScoreUnavailable[\s\S]*?\n\}/)?.[0] || "";
  assert.ok(unavailable, "isHealthScoreUnavailable is missing");
  assert.match(unavailable, /health_score_status/);
  assert.match(unavailable, /status === "insufficient_evidence"/);
  assert.match(source, /<ScoreRing score=\{healthScore\} unavailable=\{scoreUnavailable\} \/>/);
});
