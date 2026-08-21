import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { buildRepairGroupSummaries } from "../../src/lib/repairSuggestions.js";
import { buildFixListPresentation, sectionCustomerRepairs } from "../../src/lib/repairPresentation.js";

const componentSource = fs.readFileSync(
  new URL("../../src/components/fixlist/RepairGroupSummary.jsx", import.meta.url),
  "utf8",
);
const sectionListSource = fs.readFileSync(
  new URL("../../src/components/fixlist/RepairSectionList.jsx", import.meta.url),
  "utf8",
);

function templateRepair(id, family, pages) {
  return {
    id,
    rule: "missing_meta_description",
    action_priority: "important",
    page_template_family: family,
    shared_repair_confirmed: true,
    affected_pages: pages,
    page_count: pages.length,
    issue_title: `Add search descriptions to ${family}`,
  };
}

test("repairs that are the same template problem roll up into one fix-once summary", () => {
  const groups = buildRepairGroupSummaries([
    { item: templateRepair("a", "activity_detail", ["/a/1", "/a/2"]) },
    { item: templateRepair("b", "collection_page", ["/c/1", "/c/2"]) },
    { item: templateRepair("c", "standard", ["/s/1"]) },
  ]);

  assert.equal(groups.length, 1);
  const [group] = groups;
  assert.equal(group.title, "Improve search descriptions");
  assert.equal(group.repairCount, 3);
  assert.equal(group.pageCount, 5);
  assert.equal(group.templateCount, 3);
  assert.match(group.fixOnce, /shared templates/i);
});

test("group page counts are deduplicated across overlapping repairs", () => {
  const groups = buildRepairGroupSummaries([
    { item: templateRepair("a", "activity_detail", ["/shared", "/a"]) },
    { item: templateRepair("b", "collection_page", ["/shared", "/c"]) },
  ]);

  assert.equal(groups[0].pageCount, 3);
  assert.equal(groups[0].pageCountExact, true);
  assert.equal(groups[0].reportedPageCount, 4);
});

test("a group whose members carry fewer URLs than they report is marked inexact", () => {
  const groups = buildRepairGroupSummaries([
    { item: { id: "a", rule: "missing_meta_description", shared_repair_confirmed: true, page_template_family: "standard", affected_pages: ["/a"], page_count: 40 } },
    { item: { id: "b", rule: "missing_meta_description", shared_repair_confirmed: true, page_template_family: "blog", affected_pages: ["/b"], page_count: 9 } },
  ]);

  assert.equal(groups[0].pageCountExact, false);
  assert.equal(groups[0].pageCount, 2);
  assert.equal(groups[0].reportedPageCount, 49);
});

test("a single repair is never presented as a group", () => {
  assert.deepEqual(buildRepairGroupSummaries([{ item: templateRepair("a", "activity_detail", ["/a"]) }]), []);
});

test("page-level and unrecognized repairs are never grouped", () => {
  const groups = buildRepairGroupSummaries([
    { item: { id: "p1", rule: "missing_meta_description", page_count: 1, affected_pages: ["/one"] } },
    { item: { id: "p2", rule: "missing_meta_description", page_count: 1, affected_pages: ["/two"] } },
    { item: { id: "u1", rule: "unmapped_rule", page_count: 4, page_template_family: "standard" } },
    { item: { id: "u2", rule: "unmapped_rule", page_count: 4, page_template_family: "standard" } },
  ]);

  assert.deepEqual(groups, []);
});

test("grouping is a summary: every grouped repair keeps its own row and evidence", () => {
  const items = [
    templateRepair("a", "activity_detail", ["/a/1", "/a/2"]),
    templateRepair("b", "collection_page", ["/c/1"]),
    templateRepair("c", "standard", ["/s/1"]),
  ];
  const [section] = sectionCustomerRepairs(items);

  assert.equal(section.totalCount, 3);
  assert.equal(section.rows.length, 3);
  assert.equal(section.groups.length, 1);
  assert.equal(section.groups[0].repairCount, 3);

  // The rows still carry the untouched repairs, including their affected pages.
  assert.deepEqual(section.rows.map((row) => row.item.id), ["a", "b", "c"]);
  assert.deepEqual(section.rows[0].item.affected_pages, ["/a/1", "/a/2"]);
  assert.deepEqual(section.groups[0].memberIds, ["a", "b", "c"]);
  for (const row of section.rows) {
    assert.equal(row.item.rule, "missing_meta_description");
    assert.ok(row.suggestion.suggestionAvailable);
  }
});

test("legacy presentation also receives group summaries and keeps every legacy row", () => {
  const items = [
    templateRepair("a", "activity_detail", ["/a/1"]),
    templateRepair("b", "collection_page", ["/c/1"]),
  ];
  const presentation = buildFixListPresentation(items);

  assert.equal(presentation.canonical, false);
  assert.equal(presentation.legacySections[0].rows.length, 2);
  assert.equal(presentation.legacySections[0].groups.length, 1);
});

test("the group summary component states that grouped repairs remain individually fixable", () => {
  assert.match(componentSource, /Fix once: /);
  assert.match(componentSource, /group\.title/);
  assert.match(componentSource, /group\.pageCount/);
  assert.match(componentSource, /group\.templateCount/);
  assert.match(componentSource, /"template" : "templates"/);
  assert.match(componentSource, /group\.pageCountExact === false \? "\+" : ""/);
  assert.match(componentSource, /keeps its own evidence and affected URLs/);
  assert.doesNotMatch(componentSource, /fetch\(/);
  assert.doesNotMatch(componentSource, /base44/);
});

test("the section list renders group summaries above rows without replacing them", () => {
  assert.match(sectionListSource, /import RepairGroupSummary/);
  assert.match(sectionListSource, /<RepairGroupSummary groups=\{section\.groups \|\| \[\]\} \/>/);
  assert.match(sectionListSource, /visibleRows\.map\(\(row, index\) => \(/);
  assert.match(sectionListSource, /<CanonicalRepairRow/);
});
