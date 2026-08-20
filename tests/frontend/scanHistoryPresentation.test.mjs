import assert from "node:assert/strict";
import test from "node:test";

import { scanHistoryLineagePresentation } from "../../src/lib/scanHistoryPresentation.js";

test("explicit previous scan lineage may label a saved row as a rescan", () => {
  const model = scanHistoryLineagePresentation({
    id: "scan-new",
    previous_scan_id: "scan-old",
  });

  assert.equal(model.state, "explicit_rescan_lineage");
  assert.equal(model.label, "Rescan");
  assert.equal(model.parentScanId, "scan-old");
  assert.equal(model.comparisonClaimAllowed, false);
});

test("explicit rescan_of_scan_id takes precedence as the direct lineage field", () => {
  const model = scanHistoryLineagePresentation({
    previous_scan_id: "older-lineage",
    rescan_of_scan_id: "direct-parent",
  });

  assert.equal(model.parentScanId, "direct-parent");
});

test("score movement or fewer repairs cannot manufacture a rescan or improvement claim", () => {
  assert.equal(scanHistoryLineagePresentation({
    health_score: 98,
    previous_health_score: 62,
    total_fixes: 2,
    previous_total_fixes: 18,
  }), null);
});

test("lineage label never implies improved worsened or fixed", () => {
  const model = scanHistoryLineagePresentation({ previousScanId: "parent" });
  const text = JSON.stringify(model);

  assert.doesNotMatch(text, /improved|worsened|fixed|better|worse/i);
  assert.equal(model.comparisonClaimAllowed, false);
});
