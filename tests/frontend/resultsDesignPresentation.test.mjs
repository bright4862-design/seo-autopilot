import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "esbuild";

// Exercise the actual results renderer. Only remote reads and analytics are
// replaced: neither is allowed during this local presentation regression.
const result = await build({
  entryPoints: [resolve("src/pages/FixList.jsx")], bundle: true, write: false,
  platform: "node", format: "cjs", jsx: "automatic", mainFields: ["module", "main"],
  alias: { "@": resolve("src") }, external: ["react", "react/*", "react-dom", "react-dom/*", "react-router-dom"],
  plugins: [{ name: "results-without-remote-services", setup(builder) {
    builder.onResolve({ filter: /\/api\/base44Client(?:\.js)?$/ }, () => ({ path: "base44Client", namespace: "no-live-services" }));
    builder.onLoad({ filter: /.*/, namespace: "no-live-services" }, () => ({ contents: "export const base44 = {};" }));
    builder.onResolve({ filter: /(?:\/lib\/(?:scanRuns|scanHistory|analytics)|\/components\/billing\/UnlockAccessButton)(?:\.jsx?)?$/ }, (args) => ({ path: args.path, namespace: "results-boundary" }));
    builder.onLoad({ filter: /.*/, namespace: "results-boundary" }, ({ path }) => ({ contents:
      path.endsWith("scanRuns") ? "export const getScanComparison = async () => null; export const getScanRunWithFixList = () => null; export const listAccountScanRuns = () => []; export const customerRecoveryFailure = () => null;"
        : path.endsWith("scanHistory") ? "export const deleteScanRun = () => null;"
          : path.endsWith("analytics") ? "export const trackEvent = () => null;"
            : "export default function UnlockAccessButton() { return null; }",
    }));
  } }],
});
const nativeRequire = createRequire(import.meta.url);
let directHooks = false;
let directScanRecord = null;
let stateIndex = 0;
const hooks = {
  ...React,
  useState: (initial) => directHooks
    ? [stateIndex++ === 0 && directScanRecord ? directScanRecord : typeof initial === "function" ? initial() : initial, () => {}]
    : React.useState(initial),
  useEffect: (...args) => directHooks ? undefined : React.useEffect(...args),
  useMemo: (factory, deps) => directHooks ? factory() : React.useMemo(factory, deps),
  useRef: (initial) => directHooks ? { current: initial } : React.useRef(initial),
  useId: () => directHooks ? "results-export-test" : React.useId(),
};
const downloads = [];
const blobs = new Map();
class BrowserURL extends URL {
  static createObjectURL(blob) {
    const url = `blob:results-test-${blobs.size}`;
    blobs.set(url, blob);
    return url;
  }
  static revokeObjectURL() {}
}
const browserDocument = {
  body: { appendChild() {} },
  addEventListener() {}, removeEventListener() {},
  createElement(tag) {
    assert.equal(tag, "a");
    return { href: "", download: "", click() { downloads.push({ filename: this.download, blob: blobs.get(this.href) }); }, remove() {} };
  },
};
const browser = {
  addEventListener() {}, removeEventListener() {},
  setTimeout: () => 0, clearTimeout() {},
  localStorage: { getItem: () => null },
};
const module = { exports: {} };
new Function("require", "module", "exports", "window", "document", "URL", result.outputFiles[0].text)(
  (name) => name === "react" ? hooks : name === "react-router-dom"
    ? { ...nativeRequire(name), useNavigate: () => () => {}, useSearchParams: () => [new URLSearchParams(`scan_id=${scanId}`)] }
    : nativeRequire(name), module, module.exports, browser, browserDocument, BrowserURL,
);
const { CustomerCanonicalRepairs } = module.exports;
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
const scanId = "scan-design-regression";

function canonicalProps(band = "important") {
  const cards = [
    { rule: "missing_h1", title: "Review the first heading", actionPriority: band, whatToChange: "Keep the saved alpha instruction.", whyItMatters: "Alpha evidence.", who: "Developer", customerCategory: "Headings", evidence: { pageCount: 50, affectedPages: ["https://example.com/alpha", "https://example.com/alpha-two"], mergedFromFixIds: ["alpha"] } },
    { rule: "missing_h1", title: "Review the first heading", actionPriority: band, whatToChange: "Keep the separate beta instruction.", whyItMatters: "Beta evidence.", who: "Developer", customerCategory: "Headings", evidence: { pageCount: 1, affectedPages: ["https://example.com/beta"], mergedFromFixIds: ["beta"] } },
    { rule: "future_rule", title: "Review the remaining observation", actionPriority: "review", whatToChange: "Keep the saved gamma instruction.", whyItMatters: "Gamma evidence.", who: "You", customerCategory: "Page content", evidence: { pageCount: 1, affectedPages: ["https://example.com/gamma"], mergedFromFixIds: ["gamma"] } },
  ];
  const recommendations = cards.map((card, index) => ({ fix_id: ["alpha", "beta", "gamma"][index], rule: card.rule, title: card.title, recommendation: card.whatToChange, action_priority: card.actionPriority, affected_pages: card.evidence.affectedPages, page_count: card.evidence.pageCount }));
  return {
    requestedScanId: scanId, customerRepairCards: cards,
    scanRecord: { id: scanId, scan_id: scanId, website_url: "https://example.com", customer_access: "full", authority_verified: true, status: "complete", release_gate_eligible: true, is_authoritative: true, total_fixes: 3, recommendations },
  };
}

test("only the first actual canonical repair opens initially when Fix first has no cards", () => {
  const input = canonicalProps();
  const original = structuredClone(input);
  const html = render(CustomerCanonicalRepairs, input);
  const articles = [...html.matchAll(/<article\b[^>]*>([\s\S]*?)<\/article>/g)].map((match) => match[1]);
  assert.equal(articles.length, 3, "same-title repairs remain distinct");
  const open = articles.map((article) => {
    const disclosure = article.match(/<details\b([^>]*)>\s*<summary\b[^>]*>([\s\S]*?)<\/summary>/);
    assert.ok(disclosure, "each canonical repair is an accessible disclosure");
    assert.ok(disclosure[2].includes("Review"), "the repair title belongs in its disclosure summary");
    return /\bopen(?:\s|=|$)/.test(disclosure[1]);
  });
  assert.deepEqual(open, [true, false, false], "initial expansion is global, not once per priority section");
  assert.deepEqual(input, original, "presentation must not rewrite authenticated repair data");
});

test("collapsing repairs preserves distinct canonical order, exact instructions, URLs and partial affected counts", () => {
  const input = canonicalProps();
  const before = structuredClone(input);
  const html = render(CustomerCanonicalRepairs, input);
  const articles = [...html.matchAll(/<article\b[^>]*>([\s\S]*?)<\/article>/g)].map((match) => match[1]);
  assert.equal(articles.length, 3);
  assert.ok(articles[0].includes("Keep the saved alpha instruction."));
  assert.ok(articles[1].includes("Keep the separate beta instruction."));
  assert.ok(articles[2].includes("Keep the saved gamma instruction."));
  assert.match(articles[0], /50 affected pages/);
  assert.match(articles[0], /contains 2 of those URLs/);
  assert.match(articles[0], /href="https:\/\/example\.com\/alpha"/);
  assert.match(articles[0], /href="https:\/\/example\.com\/alpha-two"/);
  assert.match(articles[1], /href="https:\/\/example\.com\/beta"/);
  assert.doesNotMatch(html, /Mark as done|Mark done/);
  assert.deepEqual(input, before);
});

test("the first repair opens when the only populated canonical section is Review", () => {
  const input = canonicalProps("review");
  const html = render(CustomerCanonicalRepairs, input);
  const articles = [...html.matchAll(/<article\b[^>]*>([\s\S]*?)<\/article>/g)].map((match) => match[1]);
  const states = articles.map((article) => {
    const first = article.match(/<details\b([^>]*)>/);
    assert.ok(first);
    return /\bopen(?:\s|=|$)/.test(first[1]);
  });
  assert.deepEqual(states, [true, false, false]);
});

test("a limited result keeps its findings and evidence without authority-only guidance", () => {
  const input = canonicalProps();
  input.scanRecord = { ...input.scanRecord, status: "limited", authority_verified: false, release_gate_eligible: false, is_authoritative: false, result_integrity_verified: true, score_is_provisional: true };
  const before = structuredClone(input);
  const html = render(CustomerCanonicalRepairs, input);
  assert.equal((html.match(/<article\b/g) || []).length, 3);
  assert.match(html, /Keep the saved alpha instruction\./);
  assert.match(html, /Keep the separate beta instruction\./);
  assert.match(html, /50 affected pages/);
  assert.doesNotMatch(html, /Business decision|Explain for|Mark as done/);
  assert.deepEqual(input, before);
});

function summaryProps(overrides = {}) {
  return {
    scanRecord: { id: scanId, status: "complete", website_url: "https://example.com", created_at: "2026-10-16T10:20:00Z" },
    websiteHost: "example.com", healthScore: 58, scoreUnavailable: false,
    pagesScanned: 91, pagesFound: 5000, repairCount: 3,
    children: React.createElement("button", { type: "button" }, "Scan again"),
    ...overrides,
  };
}

test("compact results summary names the host and keeps measured score, date, coverage and Scan again", () => {
  assert.equal(typeof module.exports.CustomerResultsSummary, "function", "export the real summary component for renderer coverage");
  const html = render(module.exports.CustomerResultsSummary, summaryProps());
  assert.match(html, /<h1\b[^>]*>example\.com<\/h1>/);
  assert.match(html, /Site health score 58/);
  assert.match(html, /<svg\b[^>]*width="64"[^>]*height="64"/);
  assert.match(html, /Oct\s+16|16\s+Oct/);
  assert.match(html, /91/);
  assert.match(html, /5,000/);
  assert.match(html, /3 (?:fixes|repairs|recommendations)/);
  assert.match(html, /Scan again/);
  assert.doesNotMatch(html, /Explain for|Take this list with you/);
});

test("limited summary labels the scan and withholds the stored provisional score", () => {
  assert.equal(typeof module.exports.CustomerResultsSummary, "function");
  const input = summaryProps({ scanRecord: { status: "limited", created_at: "2026-10-16T10:20:00Z" }, healthScore: 55, scoreUnavailable: true, pagesScanned: 1, pagesFound: 1 });
  const html = render(module.exports.CustomerResultsSummary, input);
  assert.match(html, /Limited scan/);
  assert.match(html, /Site health score unavailable/);
  assert.match(html, /—/);
  assert.doesNotMatch(html, /Site health score 55|>55</);
});

function exportProps() {
  const input = canonicalProps();
  return { scanRecord: input.scanRecord, cards: input.customerRepairCards, issues: input.scanRecord.recommendations,
    healthScore: 55, scoreUnavailable: true, pagesScanned: 91, pagesFound: 5000, businessName: "Example", summary: "Checked-page evidence only." };
}

test("exports live behind one initially collapsed Export disclosure", () => {
  assert.equal(typeof module.exports.ScanExportControls, "function", "export the existing real export controls");
  const html = render(module.exports.ScanExportControls, exportProps());
  assert.equal((html.match(/<details\b/g) || []).length, 1);
  const details = html.match(/<details\b([^>]*)>/);
  assert.doesNotMatch(details[1], /\bopen(?:\s|=|$)/);
  assert.match(html, /<summary\b[^>]*aria-expanded="false"[^>]*>/);
  assert.match(html, /<summary\b[^>]*>[\s\S]*?Export[\s\S]*?<\/summary>/);
  assert.match(html, /Download PDF/);
  assert.match(html, /ChatGPT|Claude|JSON/);
  assert.match(html, /Copy/);
  assert.doesNotMatch(html, /role="menu"|Take this list with you/);
});

function textOf(node) {
  if (typeof node === "string" || typeof node === "number") return String(node);
  return React.isValidElement(node) ? React.Children.toArray(node.props.children).map(textOf).join(" ") : "";
}
function findButton(node, predicate) {
  if (!React.isValidElement(node)) return null;
  if (node.type === "button" && predicate(textOf(node))) return node;
  for (const child of React.Children.toArray(node.props.children)) {
    const match = findButton(child, predicate);
    if (match) return match;
  }
  return null;
}

test("the JSON menu action downloads the actual distinct repairs and never exports an unavailable score", async () => {
  assert.equal(typeof module.exports.ScanExportControls, "function");
  const input = exportProps();
  const original = structuredClone(input);
  downloads.length = 0;
  let tree;
  directHooks = true; stateIndex = 0;
  try { tree = module.exports.ScanExportControls(input); } finally { directHooks = false; }
  const button = findButton(tree, (label) => /Download/.test(label) && /JSON|ChatGPT|Claude/.test(label));
  assert.ok(button, "the menu exposes the existing JSON download action");
  button.props.onClick({ currentTarget: { closest: () => ({ open: true }) } });
  assert.equal(downloads.length, 1, "the real handler starts a file download");
  assert.match(downloads[0].filename, /\.json$/);
  const payload = JSON.parse(await downloads[0].blob.text());
  assert.equal(payload.fix_count, 3);
  assert.deepEqual(payload.fixes.map((fix) => fix.what_to_change), ["Keep the saved alpha instruction.", "Keep the separate beta instruction.", "Keep the saved gamma instruction."]);
  assert.deepEqual(payload.fixes.map((fix) => fix.pages_affected), [50, 1, 1]);
  assert.equal(payload.fixes[0].example_pages_are_partial, true);
  assert.equal(payload.health_score, null);
  assert.equal(payload.health_score_available, false);
  assert.deepEqual(input, original);
});

function savedRecord(overrides = {}) {
  const input = canonicalProps();
  return {
    ...input.scanRecord, health_score: 58, created_at: "2026-10-16T10:20:00Z", pages_crawled: 91, pages_found: 5000,
    recommendations: input.scanRecord.recommendations.map((row, index) => ({
      ...row, rule: `design_fixture_${index}`, recommended_value: row.recommendation, priority: "medium", evidence_class: "confirmed_problem",
      priority_reason: "Observed in the checked page evidence.", category: "other",
      repair_contract_version: "repair_contract_v2_shadow_calibrated", repair_snapshot_contract_version: "repair_contract_v2_shadow_calibrated",
      repair_snapshot_contract_complete: true, canonical_action_rank: index, repair_fingerprint: `design-${index}`,
    })),
    health_score_explanation: { version: "health_score_explanation_v1", starting_score: 100, final_score: 58,
      total_deduction: 42, deductions: [{ category: "Page content", points: 42 }], coverage_ceiling: 100,
      applied_ceiling: 100, ceiling_reason: "", floor_applied: false, verification_findings_excluded: true },
    ...overrides,
  };
}

function renderSavedPage(record) {
  directHooks = true; directScanRecord = record; stateIndex = 0;
  let tree;
  try { tree = module.exports.default(); } finally { directHooks = false; directScanRecord = null; }
  return renderToStaticMarkup(tree);
}

function assertClosedDisclosure(html, label) {
  const labelIndex = html.indexOf(label);
  assert.ok(labelIndex >= 0, `${label} is available`);
  const start = html.lastIndexOf("<details", labelIndex);
  assert.ok(start >= 0, `${label} belongs to a disclosure`);
  const tag = html.slice(start, html.indexOf(">", start) + 1);
  assert.doesNotMatch(tag, /\bopen(?:\s|=|>)/, `${label} starts collapsed`);
}

test("the actual saved-results page puts fixes before optional report detail and collapses score arithmetic", () => {
  const html = renderSavedPage(savedRecord());
  const firstInstruction = html.indexOf("Keep the saved alpha instruction.");
  const lastInstruction = html.indexOf("Keep the saved gamma instruction.");
  assert.ok(firstInstruction >= 0 && lastInstruction > firstInstruction, "the actual canonical fix list remains readable");
  assert.ok(html.indexOf("Report details") > lastInstruction, "optional report details follow all canonical actions");
  assertClosedDisclosure(html, "Report details");
  assertClosedDisclosure(html, "Why this score?");
  assert.match(html, /Site health score 58/);
  assert.match(html, /Scan again/);
  assert.doesNotMatch(html, /Explain for|Mark as done|Take this list with you/);
});

test("the actual limited saved-results page preserves the limitation and findings while hiding score 55", () => {
  const record = savedRecord({ status: "limited", authority_verified: false, release_gate_eligible: false,
    is_authoritative: false, result_integrity_verified: true, score_is_provisional: true,
    health_score: 55, health_score_status: "insufficient_evidence", limitation: "Only one page could be checked in this scan.",
    pages_crawled: 1, pages_found: 1 });
  const html = renderSavedPage(record);
  assert.match(html, /Limited scan/);
  assert.match(html, /Site health score unavailable/);
  assert.doesNotMatch(html, /Site health score 55|>55</);
  assert.match(html, /Only one page could be checked in this scan\./);
  assert.match(html, /Keep the saved alpha instruction\./);
  assert.match(html, /Keep the separate beta instruction\./);
});
