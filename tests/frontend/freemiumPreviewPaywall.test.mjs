import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import * as scanEntitlement from "../../base44/functions/startStandardScanJob/entitlement.js";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResult/projection.js";

const APP_ID = "6a498732ec779dfaaeab0e53";
const PLAN_ID = "standard150_lifetime";
const USER = { id: "user_preview_1", email: "preview@example.com" };

function pendingAccess(overrides = {}) {
  return {
    id: "access_preview_1",
    owner_user_id: USER.id,
    user_email: USER.email,
    access_status: "pending",
    has_full_access: false,
    plan_id: PLAN_ID,
    app_id: APP_ID,
    grant_source: "checkout_pending",
    ...overrides,
  };
}

function paidAccess() {
  return {
    ...pendingAccess(),
    access_status: "active",
    has_full_access: true,
    grant_source: "stripe_checkout",
    stripe_checkout_session_id: "cs_paid_preview_1",
    paid_at: "2026-09-11T00:00:00.000Z",
  };
}

test("unpaid customers receive exactly one preview scan before payment", () => {
  assert.equal(typeof scanEntitlement.evaluateScanAccess, "function");

  assert.deepEqual(
    scanEntitlement.evaluateScanAccess({ rows: [], user: USER, priorRuns: [] }),
    { ok: true, preview: true, needsAccessRecord: true },
  );

  assert.deepEqual(
    scanEntitlement.evaluateScanAccess({ rows: [pendingAccess()], user: USER, priorRuns: [] }),
    { ok: true, preview: true, needsAccessRecord: false, record: pendingAccess() },
  );

  assert.deepEqual(
    scanEntitlement.evaluateScanAccess({
      rows: [pendingAccess()],
      user: USER,
      priorRuns: [{ id: "scan_done", status: "complete" }],
    }),
    { ok: false, preview: true, failureCode: "preview_scan_used" },
  );

  const paid = scanEntitlement.evaluateScanAccess({
    rows: [paidAccess()],
    user: USER,
    priorRuns: [{ id: "scan_done", status: "complete" }],
  });
  assert.equal(paid.ok, true);
  assert.equal(paid.preview, false);
  assert.equal(paid.record.id, "access_preview_1");
});

test("unpaid verified results expose only a three-item teaser", () => {
  const run = {
    id: "scan_preview_1",
    project_id: "project_preview_1",
    website_url: "https://example.com/",
    normalized_domain: "example.com",
    status: "complete",
    release_gate_eligible: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
    health_score: 61,
    health_grade: "Needs work",
    pages_found: 120,
    pages_crawled: 150,
  };
  const fixList = {
    id: "fixlist_preview_1",
    total_fixes: 7,
    critical_count: 1,
    high_count: 3,
    medium_count: 2,
    low_count: 1,
    health_score: 61,
    health_grade: "Needs work",
  };
  const fixItems = Array.from({ length: 5 }, (_, index) => ({
    id: `row_${index + 1}`,
    fix_id: `fix_${index + 1}`,
    issue_title: `Preview issue ${index + 1}`,
    customer_category: "Technical SEO",
    priority: index === 0 ? "critical" : "high",
    action_priority: index < 2 ? "fix_first" : "improve",
    page_count: index + 2,
    page_url: `https://example.com/private-${index + 1}`,
    affected_pages: [`https://example.com/private-${index + 1}`],
    source_pages: [`https://example.com/source-${index + 1}`],
    plain_english_explanation: "Private explanation",
    why_it_matters: "Private why",
    current_value: "Private current value",
    recommended_value: "Private recommendation",
    simple_next_step: "Private next step",
    what_to_do_steps: ["Private step"],
  }));

  const preview = buildCustomerProjection({
    run,
    fixList,
    fixItems,
    fullAccess: false,
    previewAccess: true,
    authorityVerified: true,
  });

  assert.equal(preview.access, "preview");
  assert.equal(preview.authority_verified, true);
  assert.equal(preview.run.health_score, 61);
  assert.equal(preview.fixList.total_fixes, 7);
  assert.equal(preview.fixItems.length, 3);

  const forbidden = new Set([
    "page_url",
    "affected_pages",
    "source_pages",
    "plain_english_explanation",
    "why_it_matters",
    "current_value",
    "recommended_value",
    "simple_next_step",
    "what_to_do_steps",
    "raw_finding",
  ]);
  for (const item of preview.fixItems) {
    for (const key of forbidden) assert.equal(key in item, false, `${key} leaked into unpaid preview`);
  }
});

test("frontend and live V3 paths are wired for preview-before-payment", () => {
  const form = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
  const access = readFileSync("src/lib/access.js", "utf8");
  const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
  const dispatcher = readFileSync("base44/functions/startStandardScanJobV3/entry.ts", "utf8");
  const reader = readFileSync("base44/functions/getCustomerScanResultV3/entry.ts", "utf8");

  assert.match(access, /canScan:\s*fullAccess\s*\|\|\s*previewEligible/);
  assert.match(dispatcher, /evaluateScanAccess/);
  assert.match(dispatcher, /preview_scan_used/);
  assert.match(reader, /previewAccess:\s*!access\.ok/);
  assert.match(fixList, /customer_access === "preview"/);
  assert.match(fixList, /<PreviewResultState/);
  assert.match(form, /preview_scan_used/);
});
