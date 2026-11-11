import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "esbuild";
import { buildScanRunFields } from "../../src/lib/scanRunModel.js";

const result = await build({
  entryPoints: [resolve("src/pages/FixList.jsx")], bundle: true, write: false,
  platform: "node", format: "cjs", jsx: "automatic", alias: { "@": resolve("src") },
  external: ["react", "react/*", "react-dom", "react-dom/*", "react-router-dom"],
  plugins: [{ name: "no-remote-services", setup(builder) {
    builder.onLoad({ filter: /\/src\/pages\/FixList\.jsx$/ }, ({ path }) => ({
      contents: `${readFileSync(path, "utf8")}\nexport { PreviewResultState };`, loader: "jsx",
    }));
    builder.onResolve({ filter: /\/api\/base44Client(?:\.js)?$/ }, () => ({ path: "client", namespace: "fixture" }));
    builder.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({ contents: "export const base44 = {};" }));
  } }],
});
const module = { exports: {} };
new Function("require", "module", "exports", result.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const { CustomerCanonicalRepairs, CustomerResultsSummary, PreviewResultState } = module.exports;
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));

test("server priorities lead the results and all original fixes remain behind a collapsed disclosure", () => {
  const cards = ["a", "b", "c", "d"].map((fixId, index) => ({
    fixId, title: `Fix ${fixId}`, whyItMatters: `Reason ${fixId}`, who: index === 0 ? "Developer" : "You",
    whatToChange: `Instruction ${fixId}`, evidence: { pageCount: 1, affectedPages: [`https://example.com/${fixId}`], mergedFromFixIds: [] },
  }));
  const html = render(CustomerCanonicalRepairs, {
    scanRecord: { website_url: "https://example.com", top_fix_ids: ["b", "a"] }, customerRepairCards: cards,
  });
  assert.match(html, /Start with these 2/);
  assert.ok(html.indexOf("Fix b") < html.indexOf("Fix a"));
  assert.equal((html.match(/Show me how/g) || []).length, 2);
  assert.match(html, /Copy brief for my web person/);
  assert.match(html, /<details[^>]*><summary[^>]*>See all 4 fixes/);
  assert.doesNotMatch(html, /<details[^>]*open[^>]*><summary[^>]*>See all/);
  for (const id of ["a", "b", "c", "d"]) assert.match(html, new RegExp(`Instruction ${id}`));
});

test("a capped inventory never implies that the inventory is the complete site", () => {
  const html = render(CustomerResultsSummary, {
    scanRecord: { pages_crawled: 450, pages_found: 5000, inventory_capped: true, top_fix_ids: ["a"] },
    pagesScanned: 450, pagesFound: 5000,
  });
  assert.match(html, /We checked 450 pages out of at least 5,000 found/);
  assert.match(html, /1 thing is worth fixing first/);
});

test("saved models retain the 500-page count while per-fix lists keep their separate contract", () => {
  const fields = buildScanRunFields({ page_cap: 500, scan_mode: "standard_500", pages_crawled: 476, pages_planned: 500 });
  assert.equal(fields.page_cap, 500);
  assert.equal(fields.pages_crawled, 476);
  assert.equal(fields.pages_planned, 500);
});

test("a lower-bound affected count is qualified in the priority card and complete evidence", () => {
  const card = { fixId: "a", title: "Repair a heading", whyItMatters: "A heading helps readers.", who: "You", whatToChange: "Add a useful heading.", where: "At least 475 pages on your site.", evidence: { pageCount: 475, pageCountIsLowerBound: true, affectedPages: ["https://example.com/a"], mergedFromFixIds: [] } };
  const html = render(CustomerCanonicalRepairs, { scanRecord: { top_fix_ids: ["a"] }, customerRepairCards: [card] });
  assert.match(html, /at least 475 pages/);
  assert.match(html, /At least 475 affected pages/);
});

test("the free preview preserves signed lower-bound wording for affected pages", () => {
  const item = { fix_id: "preview-fix", issue_title: "Review your headings", page_count: 150, affected_page_count: 475, affected_page_count_is_lower_bound: true };
  const scanRecord = { health_score: null, seo_score: null, recommendations: [item] };
  const html = render(PreviewResultState, { scanRecord });
  assert.match(html, /at least 475 pages/);
  assert.doesNotMatch(html, /150 pages/);
  const exact = render(PreviewResultState, { scanRecord: { ...scanRecord, recommendations: [{ ...item, affected_page_count_is_lower_bound: false }] } });
  assert.match(exact, /475 pages/);
  assert.doesNotMatch(exact, /at least 475/);
  assert.equal(item.affected_page_count_is_lower_bound, true);
});
