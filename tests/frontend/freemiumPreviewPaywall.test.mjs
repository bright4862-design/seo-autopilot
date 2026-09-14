import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import * as scanEntitlement from "../../base44/functions/startStandardScanJob/entitlement.js";
import { buildCustomerProjection as buildLegacyCustomerProjection } from "../../base44/functions/getCustomerScanResult/projection.js";
import { buildCustomerProjection as buildV3CustomerProjection } from "../../base44/functions/getCustomerScanResultV3/projection.js";

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

  for (const priorRun of [
    { id: "scan_failed", status: "failed" },
    { id: "scan_cancelled", status: "cancelled" },
    { id: "scan_limited", status: "limited", release_gate_eligible: false },
    { id: "scan_unsealed", status: "complete", release_gate_eligible: false },
    { id: "scan_missing_proof", status: "complete", release_gate_eligible: true, authority_proof: "" },
  ]) {
    assert.equal(
      scanEntitlement.evaluateScanAccess({ rows: [pendingAccess()], user: USER, priorRuns: [priorRun] }).ok,
      true,
      `${priorRun.id} must not consume the free preview`,
    );
  }

  const authoritativePreview = {
    id: "scan_done",
    status: "complete",
    release_gate_eligible: true,
    authority_proof: "a".repeat(64),
  };
  assert.deepEqual(
    scanEntitlement.evaluateScanAccess({
      rows: [pendingAccess()],
      user: USER,
      priorRuns: [authoritativePreview],
    }),
    { ok: false, preview: true, failureCode: "preview_scan_used" },
  );

  const paid = scanEntitlement.evaluateScanAccess({
    rows: [paidAccess()],
    user: USER,
    priorRuns: [authoritativePreview],
  });
  assert.equal(paid.ok, true);
  assert.equal(paid.preview, false);
  assert.equal(paid.record.id, "access_preview_1");
});

test("unpaid verified results show a useful bounded preview without full exportable evidence", () => {
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
    total_fixes: 10,
    critical_count: 1,
    high_count: 4,
    medium_count: 3,
    low_count: 2,
    health_score: 61,
    health_grade: "Needs work",
  };
  const fixItems = Array.from({ length: 10 }, (_, index) => ({
    id: `row_${index + 1}`,
    fix_id: `fix_${index + 1}`,
    issue_title: `Preview issue ${index + 1}`,
    customer_category: "Technical SEO",
    priority: index === 0 ? "critical" : "high",
    action_priority: index < 2 ? "fix_first" : "improve",
    action_priority_score: 100 - index,
    canonical_action_rank: index + 1,
    page_count: index + 2,
    page_url: `https://example.com/private-${index + 1}`,
    affected_pages: [
      `https://example.com/private-${index + 1}`,
      `https://example.com/private-${index + 1}-second`,
    ],
    source_pages: [`https://example.com/source-${index + 1}`],
    plain_english_explanation: `Preview explanation ${index + 1}`,
    why_it_matters: `Preview why ${index + 1}`,
    current_value: "Private current value",
    recommended_value: `Preview recommendation ${index + 1}`,
    simple_next_step: `Preview next step ${index + 1}`,
    what_to_do_steps: ["Private step"],
    family_breakdown: [{ family: "private" }],
    raw_finding: { private: true },
    difficulty: "medium",
    who_can_do_this: "SEO manager",
    requires_developer: false,
    evidence_class: "confirmed_problem",
  }));

  for (const buildCustomerProjection of [buildLegacyCustomerProjection, buildV3CustomerProjection]) {
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
    assert.equal(preview.fixList.total_fixes, 10);
    assert.equal(preview.fixItems.length, 2, "preview sends only the two teaser findings");

    const detailed = preview.fixItems;
    assert.equal(detailed.length, 2);

    detailed.forEach((item, index) => {
      assert.equal(item.preview_locked_detail, false);
      assert.equal(item.plain_english_explanation, `Preview explanation ${index + 1}`);
      assert.equal(item.why_it_matters, `Preview why ${index + 1}`);
      assert.equal(item.recommended_value, `Preview recommendation ${index + 1}`);
      assert.equal(item.preview_example_page, `https://example.com/private-${index + 1}`);
    });

    const neverPreview = new Set([
      "page_url",
      "affected_pages",
      "source_pages",
      "current_value",
      "what_to_do_steps",
      "family_breakdown",
      "raw_finding",
    ]);
    for (const item of preview.fixItems) {
      for (const key of neverPreview) assert.equal(key in item, false, `${key} leaked into unpaid preview`);
    }
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
  assert.match(fixList, /more fixes are ready/i);
  assert.match(fixList, /Unlock full FixList/i);
  assert.match(form, /preview_scan_used/);
});

test("the free preview is view-only and contains no copy, download, or export implementation", () => {
  const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
  const start = fixList.indexOf("function PreviewResultState(");
  const end = fixList.indexOf("function FixRow(", start);
  const preview = fixList.slice(start, end);

  assert.ok(start >= 0 && end > start, "preview component must be present");
  assert.match(preview, /Free preview is view-only/);
  assert.match(preview, /copy, CSV\/PDF\/JSON downloads, exports/);
  assert.match(preview, /preview_locked_detail/);
  assert.match(preview, /customerOwnerLabel/);
  assert.doesNotMatch(preview, /navigator\.clipboard/);
  assert.doesNotMatch(preview, /downloadTextFile/);
  assert.doesNotMatch(preview, /exportScanReportPdf/);
  assert.doesNotMatch(preview, /<ScanExportControls/);
});

test("customer cards label the estimate as work rather than vague effort", () => {
  const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
  assert.match(fixList, /Estimated work:/);
  assert.doesNotMatch(fixList, />Effort:<\/span>/);
});
