import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "esbuild";
import { buildRepairWorkSurfacePresentation } from "../../src/lib/repairWorkSurfacePresentation.js";
import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import { repairRoleExplanation } from "../../src/lib/repairRoleExplanations.js";

let readComparison = async () => null;
let hookHarness = null;
const boundaryHandlers = new Set();
const browser = {
  addEventListener: (_name, callback) => boundaryHandlers.add(callback),
  removeEventListener: (_name, callback) => boundaryHandlers.delete(callback),
};
const result = await build({
  entryPoints: [resolve("src/pages/FixList.jsx")], bundle: true, write: false,
  platform: "node", format: "cjs", jsx: "automatic", mainFields: ["module", "main"],
  alias: { "@": resolve("src") }, external: ["react", "react/*", "react-dom", "react-dom/*"],
  plugins: [{ name: "isolated-customer-read", setup(builder) {
    builder.onResolve({ filter: /\/api\/base44Client(?:\.js)?$/ }, () => ({ path: "base44Client", namespace: "no-live-services" }));
    builder.onLoad({ filter: /.*/, namespace: "no-live-services" }, () => ({ contents: "export const base44 = {};" }));
    builder.onResolve({ filter: /(?:\/lib\/(?:scanRuns|scanHistory|analytics)|\/components\/billing\/UnlockAccessButton)(?:\.jsx?)?$/ }, (args) => ({ path: args.path, namespace: "customer-read-test" }));
    builder.onLoad({ filter: /.*/, namespace: "customer-read-test" }, ({ path }) => ({ contents:
      path.endsWith("scanRuns") ? "export const getScanComparison = (...args) => __readComparison(...args); export const getScanRunWithFixList = () => null; export const listAccountScanRuns = () => []; export const customerRecoveryFailure = () => null;"
        : path.endsWith("scanHistory") ? "export const deleteScanRun = () => null;"
          : path.endsWith("analytics") ? "export const trackEvent = () => null;"
            : "export default function UnlockAccessButton() { return null; }",
    }));
  } }],
});
const nativeRequire = createRequire(import.meta.url);
const hooks = {
  ...React,
  useState: (...args) => hookHarness ? hookHarness.useState(...args) : React.useState(...args),
  useEffect: (...args) => hookHarness ? hookHarness.useEffect(...args) : React.useEffect(...args),
};
const module = { exports: {} };
new Function("require", "module", "exports", "window", "__readComparison", result.outputFiles[0].text)(
  (name) => name === "react" ? hooks : nativeRequire(name), module, module.exports, browser,
  (...args) => readComparison(...args),
);
const { CustomerCanonicalRepairs, CustomerScanComparison, normalizeRecommendation, normalizeDurableScanBundle, buildCustomerPageRepairPlan, prepareCustomerPageRecommendations } = module.exports;
const scanId = "scan-current";
const row = {
  fix_id: "repair-heading", rule: "missing_h1", title: "Review heading markup", recommendation: "Keep this scanner instruction.",
  action_priority: "important", affected_pages: ["https://example.com/heading"], page_count: 1,
  root_cause_evidence: { version: "root_cause_evidence_v1_verified", state: "verified", root_cause_id: "root-heading", evidence_refs: ["observation-heading"] },
};
const card = {
  rule: "missing_h1", title: "Review heading markup", actionPriority: "important", whyItMatters: "Existing generic explanation.",
  whatToChange: "Keep this canonical card instruction.", where: "On the checked page", who: "Developer", customerCategory: "Headings",
  evidence: { pageCount: 1, affectedPages: ["https://example.com/heading"], mergedFromFixIds: [row.fix_id] },
};
function bundle() {
  return {
    scan_id: scanId, access: "full", authority_verified: true,
    run: { id: scanId, status: "complete", release_gate_eligible: true, website_url: "https://example.com" },
    fixList: { total_fixes: 1, is_authoritative: true }, fixItems: [structuredClone(row)],
  };
}
function props() {
  return { scanRecord: normalizeDurableScanBundle(bundle()), requestedScanId: scanId, customerRepairCards: [structuredClone(card)] };
}
const render = (input) => renderToStaticMarkup(React.createElement(CustomerCanonicalRepairs, input));
const escaped = (text) => renderToStaticMarkup(React.createElement(React.Fragment, null, text));

test("actual canonical FixList renderer receives raw authenticated rows and changes explanation only", () => {
  const input = props();
  const original = structuredClone(input);
  const mounted = CustomerCanonicalRepairs(input);
  assert.equal(mounted.props.sourceItems, input.scanRecord.recommendations);
  assert.deepEqual(mounted.props.sourceItems[0].root_cause_evidence, row.root_cause_evidence);
  const html = render(input);
  assert.match(html, /Explain for/);
  assert.doesNotMatch(html, /Before you start|Implementation order/);
  assert.ok(html.includes(card.whatToChange), "the existing card remains the instruction surface");
  assert.ok(html.includes(escaped(repairRoleExplanation(card, "owner").explanation)));
  const originalList = mounted.props.renderCards(input.customerRepairCards, { explanationForCard: () => ({ explanation: card.whyItMatters, explanationHeading: "Why it matters" }) });
  const ownerList = mounted.props.renderCards(input.customerRepairCards, { explanationForCard: () => ({ explanation: repairRoleExplanation(card, "owner").explanation, explanationHeading: "What this means" }) });
  const developerList = mounted.props.renderCards(input.customerRepairCards, { explanationForCard: () => ({ explanation: repairRoleExplanation(card, "developer").explanation, explanationHeading: "What this means" }) });
  const originalHtml = renderToStaticMarkup(originalList);
  for (const [element, role] of [[ownerList, "owner"], [developerList, "developer"]]) {
    const actual = renderToStaticMarkup(element);
    const expected = originalHtml.replace("Why it matters</dt>", "What this means</dt>")
      .replace(escaped(card.whyItMatters), escaped(repairRoleExplanation(card, role).explanation));
    assert.equal(actual, expected, "card instructions, evidence controls, order and sections remain exact");
  }
  assert.deepEqual(input, original);
});

for (const [reason, mutate] of [
  ["preview access", (input) => { input.scanRecord.customer_access = "preview"; }],
  ["locked access", (input) => { input.scanRecord.customer_access = "locked"; }],
  ["unverified authority", (input) => { input.scanRecord.authority_verified = false; }],
  ["limited result", (input) => { input.scanRecord.status = "limited"; }],
  ["failed release gate", (input) => { input.scanRecord.release_gate_eligible = false; }],
  ["provisional score", (input) => { input.scanRecord.score_is_provisional = true; }],
  ["blocked evidence", (input) => { input.scanRecord.evidence_quality_blocking = true; }],
  ["different requested scan", (input) => { input.requestedScanId = "scan-other"; }],
  ["conflicting bundle scan ID", (input) => { input.scanRecord.scan_id = "scan-other"; }],
  ["incomplete row population", (input) => { input.scanRecord.total_fixes = 2; }],
  ["merged card population", (input) => { input.scanRecord.recommendations.push({ ...row, fix_id: "second-repair" }); input.scanRecord.total_fixes = 2; }],
]) {
  test(`${reason} cannot enable extra role or implementation guidance`, () => {
    const input = props(); mutate(input);
    const html = render(input);
    assert.doesNotMatch(html, /<select|Before you start|What this means/);
    assert.ok(html.includes(card.whatToChange));
  });
}

function stage3Row() {
  return {
    ...row, stage3_priority_factors: {
      version: "repair_priority_v3_four_factor_v1", impact: 4, reach: 0.5, page_value: 0.8, confidence: 1,
      priority_factor_score: 1.6, reach_affected_indexable: 1, reach_observed_indexable_family: 2,
      explanation: ["Sealed priority evidence"], impact_reason: "Observed", reach_state: "known", page_value_state: "known",
      page_value_role: "commercial", page_value_source: "sealed", confidence_state: "verified", score_state: "known",
      technical_base_severity: "high", technical_severity_source: "scanner",
    },
    stage3_counts: { unique_affected_page_count: 1, observation_count: 1, known_population_count: 2, displayed_sample_count: 1,
      displayed_samples: ["https://example.com/heading"], examples_partial: false, truncated_sample_count: 0 },
  };
}

test("actual page normalization preserves valid Stage-3 neighbors when one row is malformed", () => {
  const valid = stage3Row();
  const malformed = { ...valid, fix_id: "malformed", title: "Malformed neighbor", stage3_counts: { ...valid.stage3_counts, displayed_sample_count: 2 } };
  const normalized = [valid, malformed].map((item) => normalizeRecommendation(item, props().scanRecord));
  const plan = buildCustomerPageRepairPlan(buildRepairCards(normalized));
  assert.equal(plan.cards.length, 2);
  assert.equal(plan.cards[0].priorityFactors.version, "repair_priority_v3_four_factor_v1");
  assert.equal(plan.cards[1].priorityFactors, undefined);
  assert.equal(plan.presentation_mode, "stage3_per_row_degraded_v1");
  assert.deepEqual(plan.row_coverage, { total_rows: 2, stage3_complete_rows: 1, degraded_rows: 1 });
});


test("the complete page pipeline preserves canonical order and membership through normalization, planning and actual sections", () => {
  const repairContract = {
    repair_contract_version: "repair_contract_v2_shadow_calibrated",
    repair_snapshot_contract_version: "repair_contract_v2_shadow_calibrated",
    repair_snapshot_contract_complete: true,
    evidence_class: "confirmed_problem", priority_reason: "Persisted observed issue.",
  };
  const rows = [
    { ...stage3Row(), ...repairContract, fix_id: "first", rule: "missing_meta_description", priority: "low", canonical_action_rank: 0, affected_pages: ["https://example.com/first"] },
    { ...stage3Row(), ...repairContract, fix_id: "second", rule: "empty_meta_description", priority: "critical", canonical_action_rank: 1, affected_pages: ["https://example.com/second"] },
    { ...stage3Row(), ...repairContract, fix_id: "third", rule: "missing_h1", priority: "high", canonical_action_rank: 2, affected_pages: ["https://example.com/third"] },
  ].map((item) => ({ ...item, action_priority: "important", repair_fingerprint: "shared-fingerprint", page_template_family: "standard", stage3_counts: { ...item.stage3_counts, displayed_samples: item.affected_pages } }));
  rows[1].stage3_counts.displayed_sample_count = 2;
  const data = bundle(); data.fixList.total_fixes = rows.length; data.fixItems = rows;
  const scanRecord = normalizeDurableScanBundle(data);
  const originalRows = structuredClone(rows);
  const prepared = prepareCustomerPageRecommendations(scanRecord);
  assert.deepEqual(prepared.map((item) => item.id), ["first", "second", "third"], "versioned meta-description rows are not merged or severity-ranked");
  assert.deepEqual(prepared.map((item) => item.original), rows);
  const workSurface = buildRepairWorkSurfacePresentation({ snapshotItems: prepared, visibleItems: prepared, scan: scanRecord });
  assert.equal(workSurface.presentation.canonical, true);
  const plan = buildCustomerPageRepairPlan(buildRepairCards(prepared));
  assert.deepEqual(plan.cards.map((item) => item.evidence.affectedPages[0]), rows.map((item) => item.affected_pages[0]));
  assert.deepEqual(plan.row_coverage, { total_rows: 3, stage3_complete_rows: 2, degraded_rows: 1 });
  const html = render({ scanRecord, requestedScanId: scanId, customerRepairCards: plan.cards });
  const renderedCards = [...html.matchAll(/<article\b[\s\S]*?<\/article>/g)].map((match) => match[0]);
  assert.equal(renderedCards.length, 3);
  rows.forEach((item, index) => assert.ok(renderedCards[index].includes(item.affected_pages[0]), "renderer retains the exact canonical sequence inside the Important section"));
  assert.deepEqual(rows, originalRows);
});

function mountComparison(input) {
  const states = [];
  let cursor = 0;
  let effect = null;
  let cleanup = null;
  const harness = {
    useState(initial) {
      const index = cursor++;
      if (!(index in states)) states[index] = initial;
      return [states[index], (next) => { states[index] = next; }];
    },
    useEffect(callback) { effect = callback; },
  };
  const instance = {
    render(next = input) {
      cursor = 0; hookHarness = harness;
      try { return CustomerScanComparison(next); } finally { hookHarness = null; }
    },
    start() { instance.render(); cleanup = effect(); },
    stop() { cleanup?.(); },
  };
  return instance;
}
function pending() {
  let resolveResult;
  const promise = new Promise((resolve) => { resolveResult = resolve; });
  return { promise, resolve: resolveResult };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));

for (const access of ["preview", "locked"]) {
  test(`comparison reader never runs for ${access} access`, async () => {
    let calls = 0; readComparison = async () => { calls += 1; };
    const input = props(); input.scanRecord.customer_access = access;
    const view = mountComparison(input); view.start(); await settle();
    assert.equal(calls, 0); assert.equal(view.render(), null); view.stop();
  });
}

test("comparison binds the separate verified response to the requested scan and hides first-scan/loading state", async () => {
  const request = pending(); const calls = [];
  readComparison = (...args) => { calls.push(args); return request.promise; };
  const view = mountComparison(props()); view.start();
  assert.equal(view.render(), null);
  assert.deepEqual(calls, [[scanId]], "only current ID leaves the browser");
  request.resolve({ scan_id: scanId, comparison_status: "ready", comparison_verified: true, comparison: { current_scan_id: scanId } });
  await settle();
  const panel = view.render().props.children;
  assert.equal(panel.props.currentScanId, scanId);
  assert.equal(panel.props.authorityVerified, true);
  assert.equal(view.render({ ...props(), requestedScanId: "scan-other" }), null);
  view.stop();
  readComparison = async () => ({ scan_id: scanId, comparison_status: "no_previous_scan", comparison_verified: false });
  const first = mountComparison(props()); first.start(); await settle();
  assert.equal(first.render(), null); first.stop();
});

for (const [reason, response] of [
  ["foreign scan", { scan_id: "scan-other", comparison_status: "ready", comparison_verified: true, comparison: { secret: "foreign-evidence" } }],
  ["unverified comparison", { scan_id: scanId, comparison_status: "ready", comparison_verified: false, comparison: {} }],
  ["transport failure", new Error("Read failed")],
]) {
  test(`${reason} shows comparison unavailable without changing current repair props`, async () => {
    readComparison = async () => { if (response instanceof Error) throw response; return response; };
    const input = props(); const before = structuredClone(input);
    const view = mountComparison(input); view.start(); await settle();
    const html = renderToStaticMarkup(view.render());
    assert.match(html, /Comparison unavailable/);
    assert.match(html, /Your current FixList is still available/);
    assert.doesNotMatch(html, /foreign-evidence|<dl/);
    assert.deepEqual(input, before); view.stop();
  });
}

for (const boundary of ["unmount", "customer boundary"]) {
  test(`${boundary} discards an in-flight comparison response`, async () => {
    const request = pending(); readComparison = () => request.promise;
    const view = mountComparison(props()); view.start();
    if (boundary === "unmount") view.stop();
    else for (const handler of boundaryHandlers) handler();
    request.resolve({ scan_id: scanId, comparison_status: "ready", comparison_verified: true, comparison: { current_scan_id: scanId } });
    await settle();
    assert.equal(view.render(), null); view.stop();
  });
}
