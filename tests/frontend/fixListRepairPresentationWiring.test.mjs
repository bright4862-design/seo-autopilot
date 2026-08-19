import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

test("FixList gates canonical repair sections through the persisted repair contract", () => {
  assert.match(source, /import RepairSectionList from "@\/components\/fixlist\/RepairSectionList"/);
  assert.match(source, /import \{ buildFixListPresentation \} from "@\/lib\/repairPresentation"/);
  assert.match(source, /buildFixListPresentation\(active, \{ initialFixFirstLimit: 3 \}\)/);
  assert.match(source, /repairPresentation\.canonical \? \(/);
  assert.match(source, /sections=\{repairPresentation\.sections\}/);
});

test("FixList retains one frozen legacy path when canonical presentation is unavailable", () => {
  assert.match(source, /const legacyActive = repairPresentation\.legacyItems/);
  assert.match(source, /const topPriorities = legacyActive\.slice\(0, 3\)/);
  assert.match(source, /priorityBucket\(item\.priority\) === "fix_first"/);
  assert.match(source, /priorityBucket\(item\.priority\) === "improve_next"/);
  assert.match(source, /priorityBucket\(item\.priority\) === "worth_checking"/);
});

test("FixList never infers passed checks from missing repair cards", () => {
  assert.match(source, /import ExplicitPassedChecks from "@\/components\/fixlist\/ExplicitPassedChecks"/);
  assert.match(source, /<ExplicitPassedChecks scan=\{scanRecord\} \/>/);
  assert.doesNotMatch(source, /PASSED_CHECK_DEFINITIONS/);
  assert.doesNotMatch(source, /buildPassedChecks\(/);
  assert.doesNotMatch(source, /checks passed/);
});
