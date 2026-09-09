import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

test("FixList uses the shared canonical customer repair plan for visible and exported work", () => {
  assert.match(source, /import \{ buildCustomerRepairPlan \} from "@\/lib\/customerRepairPlan";/);
  assert.match(source, /const customerRepairPlan = useMemo\(/);
  assert.match(source, /const customerRepairCards = customerRepairPlan\.cards;/);
  assert.match(source, /const nextBestStep = repairPresentation\.canonical === true\s*\? customerRepairPlan\.nextBestStep/);
  assert.match(source, /<CustomerRepairList cards=\{customerRepairCards\}/);
  assert.match(source, /<ScanExportControls[\s\S]*?cards=\{customerRepairCards\}/);
});
