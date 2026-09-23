import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { transform } from "esbuild";
import { repairRoleExplanation } from "../../src/lib/repairRoleExplanations.js";
import { repairSuggestion } from "../../src/lib/repairSuggestions.js";

async function loadJsx(relativePath, replacements = {}) {
  let source = await readFile(new URL(relativePath, import.meta.url), "utf8");
  for (const [from, to] of Object.entries(replacements)) source = source.replace(JSON.stringify(from), JSON.stringify(to));
  source = source.replace('from "react"', `from ${JSON.stringify(import.meta.resolve("react"))}`);
  const compiled = await transform(source, { loader: "jsx", jsxFactory: "React.createElement", format: "esm" });
  return `data:text/javascript;base64,${Buffer.from(compiled.code).toString("base64")}`;
}
const library = (file) => new URL(`../../src/lib/${file}`, import.meta.url).href;
const roleUrl = await loadJsx("../../src/components/fixlist/RepairRoleView.jsx", {
  "../../lib/repairRoleExplanations.js": library("repairRoleExplanations.js"),
  "../../lib/repairRolePresentation.js": library("repairRolePresentation.js"),
});
// The existing role component relies on the JSX runtime rather than importing
// React. Supply it when compiling with the same classic SSR harness as its tests.
const roleCode = Buffer.from(roleUrl.split(",")[1], "base64").toString("utf8");
const completeRoleUrl = `data:text/javascript;base64,${Buffer.from(`import React from ${JSON.stringify(import.meta.resolve("react"))};\n${roleCode}`).toString("base64")}`;
const componentUrl = await loadJsx("../../src/components/fixlist/CustomerRepairGuidance.jsx", {
  "../../lib/implementationPlan.js": library("implementationPlan.js"),
  "../../lib/repairRoleExplanations.js": library("repairRoleExplanations.js"),
  "../../lib/repairSuggestions.js": library("repairSuggestions.js"),
  "./RepairRoleView.jsx": completeRoleUrl,
});
const { default: CustomerRepairGuidance, CustomerRepairGuidanceView } = await import(componentUrl);

const scanId = "scan:current";
const source = { id: "repair:heading", scan_run_id: scanId, rule: "missing_h1", title: "Check the main heading", recommendation: "Use the existing page-title field.", action_priority: "important" };
const card = { rule: source.rule, title: source.title, whatToChange: "Preserve this exact canonical instruction.", whyItMatters: "Original explanation.", evidence: { pageCount: 2, affectedPages: ["/first", "/second"] } };
const render = (props, Component = CustomerRepairGuidanceView) => renderToStaticMarkup(React.createElement(Component, props));
function renderCard(item, guidance) {
  return React.createElement("article", null,
    React.createElement("h4", null, item.title),
    React.createElement("h5", null, guidance.explanationHeading),
    React.createElement("p", { className: "explanation" }, guidance.explanation),
    React.createElement("p", { className: "instruction" }, item.whatToChange),
    React.createElement("p", { className: "evidence" }, JSON.stringify(item.evidence)));
}
const props = () => ({ sourceItems: [structuredClone(source)], cards: [structuredClone(card)], trustedScanId: scanId, sourceScanId: scanId, cardsScanId: scanId, authorityVerified: true, role: "owner", onRoleChange() {}, renderCard });
function findElement(element, predicate) {
  if (!React.isValidElement(element)) return null;
  if (predicate(element)) return element;
  for (const child of React.Children.toArray(element.props.children)) {
    const found = findElement(child, predicate);
    if (found) return found;
  }
  return null;
}
const escaped = (value) => renderToStaticMarkup(React.createElement(React.Fragment, null, value));

test("selecting a role changes visible guidance and preserves exact instructions, evidence and inputs", () => {
  const input = props();
  const before = structuredClone({ sourceItems: input.sourceItems, cards: input.cards });
  let role = "owner";
  const viewProps = () => ({ ...input, role, onRoleChange: (next) => { role = next; } });
  const ownerHtml = render(viewProps());
  const tree = CustomerRepairGuidanceView(viewProps());
  const selector = findElement(tree, (node) => node.type.name === "RepairRoleSelector");
  assert.ok(selector, "a supported repair exposes a role selector");
  const select = findElement(selector.type(selector.props), (node) => node.type === "select");
  select.props.onChange({ target: { value: "developer" } });
  const developerHtml = render(viewProps());
  assert.equal(role, "developer");
  assert.ok(ownerHtml.includes(escaped(repairRoleExplanation(card, "owner").explanation)));
  assert.ok(developerHtml.includes(escaped(repairRoleExplanation(card, "developer").explanation)));
  assert.notEqual(ownerHtml, developerHtml);
  assert.match(developerHtml, /value="developer" selected=""/);
  for (const html of [ownerHtml, developerHtml]) {
    assert.ok(html.includes(card.whatToChange));
    assert.ok(html.includes(escaped(JSON.stringify(card.evidence))));
  }
  assert.deepEqual({ sourceItems: input.sourceItems, cards: input.cards }, before);
});

test("unmapped rules retain their original explanation and have no inert role selector", () => {
  const input = props();
  input.cards[0].rule = "future_rule";
  const html = render(input);
  assert.doesNotMatch(html, /<select/);
  assert.ok(html.includes(card.whyItMatters));
  assert.ok(html.includes(card.whatToChange));
  assert.doesNotMatch(html, /Review this issue based on the evidence collected/);
});

test("mixed card coverage changes only supported explanations without joining cards to source rows", () => {
  const input = props();
  input.cards = [{ ...card, rule: "future_rule", title: "Unmapped card" }, card];
  input.renderCards = (cards, { role, explanationForCard }) => {
    assert.equal(cards, input.cards);
    assert.equal(role, "seo");
    return React.createElement("section", { "data-preserved-sections": true }, cards.map((item, index) =>
      React.createElement("div", { key: index }, renderCard(item, explanationForCard(item)))));
  };
  const html = render({ ...input, role: "seo" });
  assert.match(html, /data-preserved-sections/);
  assert.ok(html.includes(card.whyItMatters));
  assert.ok(html.includes(escaped(repairRoleExplanation(card, "seo").explanation)));
  assert.equal((html.match(new RegExp(card.whatToChange, "g")) || []).length, 2);
});

test("Funbooker repair population explains the first card and all four previously uncovered cards for each role", () => {
  // The production 2026-09-23 scan's seven rules, in its canonical order.
  const rules = ["redirect_chain", "canonical_missing", "meta_description_unusable", "meta_description_unusable", "missing_h1", "title_over_pixel_limit", "potential_orphan_pages"];
  const input = props();
  input.sourceItems = rules.map((rule, index) => ({ ...source, id: `repair:${index}`, rule, title: `Repair ${index}` }));
  input.cards = rules.map((rule, index) => ({ ...card, rule, title: `Repair ${index}` }));
  const before = structuredClone({ sourceItems: input.sourceItems, cards: input.cards });
  const expectedHeadings = { owner: "Business decision", marketing: "Content review", seo: "SEO review", developer: "Implementation guidance" };
  const copyByRole = {};
  for (const role of Object.keys(expectedHeadings)) {
    const html = render({ ...input, role });
    const articles = [...html.matchAll(/<article>([\s\S]*?)<\/article>/g)].map((match) => match[1]);
    assert.equal(articles.length, 7);
    assert.match(html, /Owner \/ CEO/);
    copyByRole[role] = articles.map((article) => {
      assert.ok(article.includes(`<h5>${expectedHeadings[role]}</h5>`));
      assert.ok(article.includes(card.whatToChange));
      assert.ok(article.includes(escaped(JSON.stringify(card.evidence))));
      assert.ok(!article.includes(card.whyItMatters));
      return article.match(/<p class="explanation">([\s\S]*?)<\/p>/)[1];
    });
  }
  for (let index = 0; index < rules.length; index += 1) {
    assert.equal(new Set(Object.values(copyByRole).map((copy) => copy[index])).size, 4, rules[index]);
  }
  // Useful responsibility and validation changes, beyond different strings.
  assert.match(copyByRole.owner[0], /maintainer/);
  assert.match(copyByRole.seo[0], /indexab|canonical/i);
  assert.match(copyByRole.developer[0], /redirect rule|routing/i);
  assert.match(copyByRole.owner[2], /content editor|content team/i);
  assert.match(copyByRole.seo[2], /missing|empty|malformed/i);
  assert.match(copyByRole.developer[2], /HTML|document head/i);
  assert.match(copyByRole.owner[5], /key message|purpose/i);
  assert.match(copyByRole.seo[5], /pixel|width/i);
  assert.match(copyByRole.developer[5], /template|generat/i);
  assert.deepEqual({ sourceItems: input.sourceItems, cards: input.cards }, before);
});

test("partial role coverage is stated beside the selector", () => {
  const input = props();
  input.cards.push({ ...card, rule: "unmapped_rule" });
  const html = render(input);
  assert.match(html, /Role guidance is available for 1 of 2 repairs/);
});

for (const [label, change] of [
  ["unverified authority", (input) => { input.authorityVerified = false; }],
  ["truthy authority string", (input) => { input.authorityVerified = "true"; }],
  ["missing trusted scan", (input) => { input.trustedScanId = ""; }],
  ["wrong scan identity", (input) => { input.sourceItems[0].scan_run_id = "scan:other"; }],
  ["conflicting original identity", (input) => { input.sourceItems[0].original = { scan_id: "scan:other" }; }],
  ["missing source population identity", (input) => { delete input.sourceScanId; }],
  ["stale source population", (input) => { input.sourceScanId = "scan:previous"; }],
  ["missing card population identity", (input) => { delete input.cardsScanId; }],
  ["stale card population", (input) => { input.cardsScanId = "scan:previous"; }],
  ["stale card scan identity", (input) => { input.cards[0].scan_id = "scan:previous"; }],
  ["stale original card identity", (input) => { input.cards[0].original = { scan_run_id: "scan:previous" }; }],
  ["no source rows", (input) => { input.sourceItems = []; }],
]) {
  test(`${label} leaves original cards readable without adding guidance`, () => {
    const input = props();
    change(input);
    const html = render(input);
    assert.doesNotMatch(html, /<select|Implementation order|What this means/);
    assert.ok(html.includes(card.whyItMatters));
    assert.ok(html.includes(card.whatToChange));
  });
}

test("V8 recommendation rows without local scan IDs use the exact authenticated population identities", () => {
  const row = { fix_id: "repair:v8", rule: "missing_h1", title: "Check the main heading", simple_next_step: "Use the existing heading field.", action_priority: "important" };
  const input = { ...props(), sourceItems: [row] };
  const html = render(input);
  assert.match(html, /<select/);
  assert.match(html, /Implementation order/);
  assert.ok(html.includes(row.simple_next_step));
  assert.deepEqual(row, { fix_id: "repair:v8", rule: "missing_h1", title: "Check the main heading", simple_next_step: "Use the existing heading field.", action_priority: "important" });
  for (const sourceScanId of [undefined, "scan:previous", { id: scanId }]) {
    const rejected = render({ ...input, sourceScanId });
    assert.doesNotMatch(rejected, /<select|Implementation order|What this means/);
    assert.ok(rejected.includes(card.whatToChange));
  }
});

test("raw implementation instructions preserve existing suggestion precedence and fallback", () => {
  for (const overrides of [
    { recommendation: "Scanner recommendation wins.", simple_next_step: "Lower-precedence step." },
    { recommendation: "", simple_next_step: "Scanner next step wins.", recommended_value: "Lower-precedence value." },
    { recommendation: "", simple_next_step: "", recommended_value: "Scanner recommended value." },
    { recommendation: "", simple_next_step: "", recommended_value: "", original: { simple_next_step: "Original scanner instruction." } },
    { recommendation: "", simple_next_step: "", recommended_value: "" },
    { recommendation: "", simple_next_step: "", recommended_value: "", rule: "unmapped_rule" },
  ]) {
    const row = { ...source, ...overrides };
    const html = render({ ...props(), sourceItems: [row], renderCards: () => null });
    assert.ok(html.includes(escaped(repairSuggestion(row).suggestedFix)));
  }
});

for (const [label, items] of [
  ["duplicate IDs", [source, { ...source }]],
  ["missing IDs", [{ ...source, id: "" }]],
  ["non-string IDs", [{ ...source, id: { hostile: true } }]],
]) {
  test(`${label} hide the implementation plan without losing cards or role copy`, () => {
    const html = render({ ...props(), sourceItems: items });
    assert.doesNotMatch(html, /Implementation order/);
    assert.match(html, /<select/);
    assert.ok(html.includes(card.whatToChange));
  });
}

const planTitles = (html) => [...html.matchAll(/<li[^>]*><p class="font-medium text-ink">([^<]*)<\/p>/g)].map((match) => match[1]);
test("implementation groups never flatten non-adjacent repairs out of canonical sequence", () => {
  const items = [
    { ...source, id: "a", title: "First repair", repair_surface: "document_head", remediation_family: "metadata" },
    { ...source, id: "b", title: "Second repair", repair_surface: "content", remediation_family: "headings" },
    { ...source, id: "c", title: "Third repair", repair_surface: "document_head", remediation_family: "metadata" },
  ];
  const html = render({ ...props(), sourceItems: items, renderCards: () => null });
  assert.deepEqual(planTitles(html), ["First repair", "Second repair", "Third repair"]);
  assert.match(html, /Related work: Third repair/);
});

test("verified explicit dependency changes execution sequence with a reason while card order stays intact", () => {
  const root = { version: "root_cause_evidence_v1_verified", state: "verified", root_cause_id: "root:redirect", evidence_refs: ["observation:redirect"] };
  const items = [
    { ...source, id: "sitemap", title: "Update sitemap", rule: "sitemap_redirect", action_priority: "fix_first", root_cause_evidence: root },
    { ...source, id: "redirect", title: "Stabilize redirect", rule: "redirect_chain", action_priority: "important", root_cause_evidence: root },
  ];
  const original = structuredClone(items);
  const input = { ...props(), sourceItems: items };
  const html = render(input);
  assert.deepEqual(planTitles(html), ["Stabilize redirect", "Update sitemap"]);
  assert.match(html, /First: Stabilize redirect/);
  assert.ok(html.includes(card.whatToChange));
  assert.deepEqual(items, original);
});

test("the default stateful wrapper starts with the owner explanation and escapes source instructions", () => {
  const input = props();
  input.sourceItems[0].recommendation = "<script>unsafe()</script>";
  const html = render(input, CustomerRepairGuidance);
  assert.ok(html.includes(escaped(repairRoleExplanation(card, "owner").explanation)));
  assert.match(html, /&lt;script&gt;unsafe\(\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});
