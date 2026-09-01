import assert from "node:assert/strict";
import test from "node:test";

import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import { buildExportRepairModel } from "../../src/lib/exportScanReport.js";

function row(fixId, fingerprint, page, status = "needs_developer") {
  return {
    id: fixId,
    fix_id: fixId,
    rule: "missing_meta_description",
    repair_fingerprint: fingerprint,
    status,
    issue_title: "Add a meta description",
    why_it_matters: "Searchers need a useful summary.",
    recommendation: "Add one page-specific description.",
    affected_pages: [page],
    page_count: 1,
  };
}

test("FixList and PDF export count the same canonical repairs", () => {
  const issues = [
    row("first", "same-fingerprint", "/fr/page"),
    row("second", "same-fingerprint", "/de/page"),
    row("third", "another-fingerprint", "/shared", "needs_approval"),
  ];

  const fixListCards = buildRepairCards(issues);
  const exported = buildExportRepairModel({ issues });

  assert.equal(fixListCards.length, 2);
  assert.equal(exported.repairCount, fixListCards.length);
  assert.equal(exported.repairs.length, fixListCards.length);
  assert.equal(exported.developer.length, 1);
  assert.equal(exported.approval.length, 1);
  assert.deepEqual(
    exported.repairs.map((repair) => repair.evidence.mergedFromFixIds),
    fixListCards.map((repair) => repair.evidence.mergedFromFixIds),
  );
});

test("distinct fingerprints on the same URL stay distinct in both surfaces", () => {
  const issues = [
    row("title", "title-fingerprint", "/shared"),
    row("canonical", "canonical-fingerprint", "/shared"),
  ];

  assert.equal(buildRepairCards(issues).length, 2);
  assert.equal(buildExportRepairModel({ issues }).repairCount, 2);
});

test("empty fingerprints stay separate in FixList and PDF export", () => {
  const issues = [
    row("missing-one", "", "/first"),
    row("missing-two", "", "/second"),
  ];

  const fixListCards = buildRepairCards(issues);
  const exported = buildExportRepairModel({ issues });

  assert.equal(fixListCards.length, 2);
  assert.equal(exported.repairCount, 2);
  assert.equal(exported.repairs.length, 2);
});
