import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

test("FixList routes the saved snapshot through the unified repair work surface", () => {
  assert.match(source, /import RepairWorkSurface from "@\/components\/fixlist\/RepairWorkSurface"/);
  assert.match(source, /import \{ buildRepairWorkSurfacePresentation \} from "@\/lib\/repairWorkSurfacePresentation"/);
  assert.match(source, /buildRepairWorkSurfacePresentation\(\{[\s\S]*snapshotItems: recommendations,[\s\S]*visibleItems: active,[\s\S]*doneIds,[\s\S]*scan: scanRecord,[\s\S]*initialFixFirstLimit: 3/);
  assert.match(source, /const repairPresentation = repairWorkSurface\.presentation/);
  assert.match(source, /<RepairWorkSurface[\s\S]*\{\.\.\.repairWorkSurface\}/);
  assert.doesNotMatch(source, /import RepairSectionList from "@\/components\/fixlist\/RepairSectionList"/);
  assert.doesNotMatch(source, /buildFixListPresentation\(active/);
});

test("FixList retains one frozen legacy path only for genuinely legacy repairs", () => {
  assert.match(source, /const legacyActive = repairPresentation\.canonical \|\| repairPresentation\.unsupported \? \[\] : repairPresentation\.legacyItems/);
  assert.match(source, /const topPriorities = legacyActive\.slice\(0, 3\)/);
  assert.match(source, /priorityBucket\(item\.priority\) === "fix_first"/);
  assert.match(source, /priorityBucket\(item\.priority\) === "improve_next"/);
  assert.match(source, /priorityBucket\(item\.priority\) === "worth_checking"/);
  assert.match(source, /!repairPresentation\.canonical && !repairPresentation\.unsupported && active\.length === 0 && doneItems\.length > 0/);
});

test("FixList fails closed on unsupported versioned repair contracts", () => {
  assert.match(source, /repairPresentation\.unsupported \? \(/);
  assert.match(source, /We can&rsquo;t safely display this saved FixList/);
  assert.match(source, /No browser-ranked substitute is being shown/);
});

test("FixList delegates zero-repair and canonical all-Done states to the unified work surface", () => {
  assert.doesNotMatch(source, /Nothing to fix in this sample\./);
  assert.doesNotMatch(source, /repairPresentation\.canonical \? \([\s\S]*<RepairSectionList/);
});

test("FixList never infers passed checks from missing repair cards", () => {
  assert.match(source, /import ExplicitPassedChecks from "@\/components\/fixlist\/ExplicitPassedChecks"/);
  assert.match(source, /<ExplicitPassedChecks scan=\{scanRecord\} \/>/);
  assert.doesNotMatch(source, /PASSED_CHECK_DEFINITIONS/);
  assert.doesNotMatch(source, /buildPassedChecks\(/);
  assert.doesNotMatch(source, /checks passed/);
});
