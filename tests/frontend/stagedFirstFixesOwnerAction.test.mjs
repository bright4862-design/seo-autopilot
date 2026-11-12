import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { topFixIds as readerTopFixIds } from "../../base44/functions/getCustomerScanResultV9/firstFixes.js";
import { topFixIds as writerTopFixIds } from "../../base44/functions/persistDurableScanAuthorityV9/firstFixes.js";
import { serverSelectedPriorityCards } from "../../src/lib/scanPresentation.js";
const topFixIds = readerTopFixIds;

function rankedFix(fixId, rank, fields = {}) {
  return {
    fix_id: fixId,
    canonical_action_rank: rank,
    root_cause_id: fixId,
    ...fields,
  };
}

const expected = ["technical-a", "technical-b", "owner-action"];

for (const field of ["who_can_do_this", "who_does_it", "implementation_owner", "raw_finding"]) {
  test(`an easy task assigned through ${field} to a specialist cannot displace the owner action`, () => {
    const specialist = field === "raw_finding"
      ? { raw_finding: { implementation_owner: "developer" } }
      : { [field]: "developer" };
    const fixes = [
      rankedFix("technical-a", 1, { ...specialist, difficulty: "easy" }),
      rankedFix("technical-b", 2, { ...specialist, difficulty: "easy" }),
      rankedFix("technical-c", 3, { ...specialist, difficulty: "easy" }),
      rankedFix("owner-action", 4, { who_can_do_this: "You", difficulty: "medium" }),
    ];
    const before = structuredClone(fixes);
    assert.deepEqual(topFixIds(fixes), expected);
    assert.deepEqual(fixes, before);
  });
}

test("the explicit owner role is normalized before reserving its first-screen slot", () => {
  const fixes = [
    ...["technical-a", "technical-b", "technical-c"].map((id, index) => rankedFix(id, index + 1, { who_can_do_this: "developer" })),
    rankedFix("owner-action", 4, { who_can_do_this: "  You  " }),
  ];
  assert.deepEqual(topFixIds(fixes), expected);
});

test("missing owner actions preserve the original priority order", () => {
  const fixes = ["technical-a", "technical-b", "technical-c", "technical-d"]
    .map((id, index) => rankedFix(id, index + 1, { who_can_do_this: "developer", difficulty: "easy" }));
  assert.deepEqual(topFixIds(fixes), ["technical-a", "technical-b", "technical-c"]);
});

test("an unknown explicit assignment does not count as an owner action", () => {
  const fixes = [
    ...["technical-a", "technical-b", "technical-c"].map((id, index) => rankedFix(id, index + 1, { who_can_do_this: "specialist", difficulty: "easy" })),
    rankedFix("owner-action", 4, { who_can_do_this: "owner" }),
  ];
  assert.deepEqual(topFixIds(fixes), expected);
});

test("difficulty alone cannot displace an explicitly owner-doable action", () => {
  const fixes = [
    rankedFix("legacy-action", 1, { difficulty: "easy" }),
    rankedFix("technical-a", 2, { who_can_do_this: "developer" }),
    rankedFix("technical-b", 3, { who_can_do_this: "developer" }),
    rankedFix("owner-action", 4, { who_can_do_this: "owner" }),
  ];
  assert.deepEqual(topFixIds(fixes), ["legacy-action", "technical-a", "owner-action"]);
});

for (const [label, select] of [["reader", readerTopFixIds], ["writer", writerTopFixIds]]) {
  for (const [source, restriction] of [["direct", { requires_developer: true }], ["retained", { raw_finding: { requires_developer: true } }]]) {
    test(`${label}: ${source} developer-only evidence overrides a contradictory owner label`, () => {
      const fixes = [
        ...["technical-a", "technical-b", "technical-c"].map((id, index) => rankedFix(id, index + 1, { who_can_do_this: "you", difficulty: "easy", ...restriction })),
        rankedFix("owner-action", 4, { who_can_do_this: "owner" }),
      ];
      assert.deepEqual(select(fixes), expected);
    });
  }

  test(`${label}: a shared owner/web-person role remains owner-doable`, () => {
    const fixes = [
      ...["technical-a", "technical-b", "technical-c"].map((id, index) => rankedFix(id, index + 1, { who_can_do_this: "developer" })),
      rankedFix("owner-action", 4, { who_can_do_this: "you_or_your_web_person" }),
    ];
    assert.deepEqual(select(fixes), expected);
  });

  test(`${label}: the shortlist follows recorded priority factors without changing canonical ranks`, () => {
    const fixes = [rankedFix("low", 1), rankedFix("high", 2), rankedFix("middle", 3), rankedFix("next", 4)];
    [0.1, 0.9, 0.5, 0.8].forEach((score, index) => { fixes[index].stage3_priority_factors = { priority_factor_score: score }; });
    const before = structuredClone(fixes);
    assert.deepEqual(select(fixes), ["high", "next", "middle"]);
    assert.deepEqual(fixes, before);
  });
}

test("writer and reader shortlist the same owner action from legacy-compatible persisted V9 data", async () => {
  const { webcrypto } = await import("node:crypto");
  const { buildAuthoritySnapshot, buildPersistedAuthoritySnapshot } = await import("../../base44/functions/persistDurableScanAuthorityV9/authoritySnapshot.js");
  const { authorityRowsFromSnapshot } = await import("../../base44/functions/persistDurableScanAuthorityV9/authorityRows.js");
  const { authoritySnapshotFromRows, createAuthoritySeal, verifyAuthoritySeal, buildCustomerProjection } = await import("../../base44/functions/getCustomerScanResultV9/projection.js");
  const geo = JSON.parse(readFileSync("tests/fixtures/geo/runtime.json", "utf8"));
  const fixes = [
    ...["technical-a", "technical-b", "technical-c"].map((id, index) => rankedFix(id, index + 1, { who_can_do_this: "developer", difficulty: "easy", priority: "high" })),
    rankedFix("owner-action", 4, { who_can_do_this: "you", priority: "low" }),
  ].map(fix => ({ ...fix, rule: fix.fix_id, issue_title: `Repair ${fix.fix_id}`, page_count: 1, affected_pages: [`https://example.com/${fix.fix_id}`], what_to_do_steps: [`Complete ${fix.fix_id}`] }));
  const snapshot = buildAuthoritySnapshot({
    scan: { ...geo.scan, scan_mode: "standard_150", page_cap: 150, pipeline_mode: "staged", website_url: "https://example.com/", pages_found: 150, pages_crawled: 150 },
    review: { geo_readiness: geo.assessed, health_score: 90, recommendations: fixes },
    identity: { scan_id: "scan_123", project_id: "project_123", normalized_domain: "example.com" },
    userId: "owner_123", now: "2026-11-11T12:00:00.000Z",
  });
  assert.equal(snapshot.fix_list.top_action_fix_ids.length, 3);
  assert.ok(snapshot.fix_list.top_action_fix_ids.includes("owner-action"));
  const saved = authorityRowsFromSnapshot(snapshot, { fixListId: "list_123", ownerUserId: "owner_123" });
  const rows = { run: { ...saved.scanRun, id: "scan_123", project_id: "project_123" }, fixList: { ...saved.fixList, id: "list_123" }, fixItems: saved.fixItems, userId: "owner_123" };
  assert.deepEqual(buildPersistedAuthoritySnapshot(rows), snapshot);
  assert.deepEqual(authoritySnapshotFromRows(rows), snapshot);
  const proof = await createAuthoritySeal(snapshot, "owner-shortlist-test-key", webcrypto);
  assert.equal(await verifyAuthoritySeal(authoritySnapshotFromRows(rows), "owner-shortlist-test-key", proof, webcrypto), true);
  const projection = buildCustomerProjection({ ...rows, fullAccess: true, authorityVerified: true });
  assert.deepEqual(projection.top_fix_ids, snapshot.fix_list.top_action_fix_ids);
  assert.equal(projection.fixItems.length, fixes.length);

  const { build } = await import("esbuild");
  const React = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { buildRepairCard } = await import("../../src/lib/repairCardModel.js");
  const bundled = await build({
    entryPoints: [resolve("src/pages/FixList.jsx")], bundle: true, write: false,
    platform: "node", format: "cjs", jsx: "automatic", alias: { "@": resolve("src") },
    external: ["react", "react/*", "react-dom", "react-dom/*", "react-router-dom"],
    plugins: [{ name: "no-remote-services", setup(builder) {
      builder.onResolve({ filter: /\/api\/base44Client(?:\.js)?$/ }, () => ({ path: "client", namespace: "fixture" }));
      builder.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({ contents: "export const base44 = {};" }));
    } }],
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", bundled.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
  const cards = projection.fixItems.map(buildRepairCard);
  assert.equal(cards.find(card => card.fixId === "owner-action").who, "You");
  const html = renderToStaticMarkup(React.createElement(module.exports.CustomerCanonicalRepairs, {
    scanRecord: { top_fix_ids: projection.top_fix_ids }, customerRepairCards: cards,
  }));
  const firstScreen = html.slice(0, html.indexOf("See all"));
  assert.match(firstScreen, /Repair owner-action/);
  assert.match(firstScreen, /You/);
  assert.equal((firstScreen.match(/Show me how/g) || []).length, 3);
  assert.match(html, /<details[^>]*><summary[^>]*>See all 4 fixes/);
  for (const fix of fixes) assert.match(html, new RegExp(`Repair ${fix.fix_id}`));
});

test("the server shortlist maps to three varied cards and retains every other repair", () => {
  const fixes = [
    rankedFix("technical-a", 1, { who_can_do_this: "developer", difficulty: "easy", page_template_family: "product" }),
    rankedFix("technical-b", 2, { who_can_do_this: "developer", difficulty: "easy", page_template_family: "blog" }),
    rankedFix("technical-c", 3, { who_can_do_this: "developer", difficulty: "easy", page_template_family: "location" }),
    rankedFix("owner-action", 4, { who_can_do_this: "you", page_template_family: "home" }),
  ];
  const cards = fixes.map(fix => ({ fixId: fix.fix_id }));
  const selection = serverSelectedPriorityCards(cards, topFixIds(fixes));
  assert.deepEqual(selection.first.map(card => card.fixId), expected);
  assert.deepEqual(selection.remaining.map(card => card.fixId), ["technical-c"]);
});
