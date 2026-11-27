import assert from "node:assert/strict";
import test from "node:test";
import { buildRepairCard, customerRepairObservationRows } from "../../src/lib/repairCardModel.js";
import { buildScanHandoff } from "../../src/lib/scanHandoff.js";

function customerCard(rule, observations, fields = {}) {
  return buildRepairCard({
    id: rule,
    rule,
    affected_pages: ["/activities/"],
    raw_finding: { repair_observation_samples: observations },
    ...fields,
  });
}

const origin = "https://example.com";

test("HTML template observations separate a source repair from a visitor-content check in the card and handoff", () => {
  for (const [kind, excerpt] of [["empty_shell", "main: No visible text, media or form in the content area."], ["placeholder_copy", "main: Lorem ipsum dolor sit amet"], ["unresolved_template", "meta: #location#"]]) {
    const item = customerCard("visible_template_content", [{ page_url: "/activities/", status: 200, issue_type: kind, excerpt }], {
      priority: "high", evidence_class: "confirmed_problem", action_priority: "important",
    });
    assert.match(item.title, /page source/);
    assert.match(item.whatToChange, /after it loads/);
    assert.match(item.whatToChange, /Correct any unfinished title or description/);
    assert.match(item.whatToChange, /fix its content or template/);
    assert.equal(item.priority, "high");
    assert.equal(item.evidenceClass, "confirmed_problem");
    assert.equal(item.actionPriority, "important");
    assert.equal(customerRepairObservationRows(item, origin)[0].valueLabel, excerpt);
    const handoff = buildScanHandoff({ scanRecord: { website_url: origin }, cards: [item] });
    assert.equal(handoff.fixes[0].what_to_change, item.whatToChange);
  }
});

test("the H1 count describes the source and an unrecorded count does not become zero", () => {
  const checked = customerCard("rendered_heading_review", [{ page_url: "/activities/", status: 200, h1_count: 0 }], {
    title: "Check the main heading in a browser", action_priority: "review", evidence_class: "opportunity",
  });
  assert.match(checked.title, /browser/);
  assert.equal(checked.actionPriority, "review");
  assert.equal(customerRepairObservationRows(checked, origin)[0].valueLabel, "H1 count in the source HTML: 0");
  const unknown = customerCard("rendered_heading_review", [{ page_url: "/activities/", status: 200, h1_count: null, excerpt: "Check the rendered heading" }]);
  assert.equal(customerRepairObservationRows(unknown, origin)[0].valueLabel, "Check the rendered heading");
});

test("missing preferred addresses and existing addresses reported to redirect need different checks", () => {
  const missing = customerCard("canonical_missing", [{ page_url: "/activities/", status: 200, canonical_url: "" }]);
  assert.match(missing.whatToChange, /which address should appear in search/);
  assert.match(missing.whatToChange, /after it loads and its HTTP headers/);
  assert.match(customerRepairObservationRows(missing, origin)[0].valueLabel, /source HTML: missing/);
  const unknown = customerCard("canonical_missing", [{ page_url: "/activities/", status: 200, canonical_url: null, excerpt: "Value unavailable" }]);
  assert.equal(customerRepairObservationRows(unknown, origin)[0].valueLabel, "Value unavailable");
  const redirect = customerCard("canonical_target_redirect", []);
  assert.match(redirect.whatToChange, /including its trailing slash/);
  assert.match(redirect.whatToChange, /update the existing setting/);
  assert.match(redirect.whatToChange, /returns 200 at the intended address, keep the setting/);
  assert.doesNotMatch(redirect.whatToChange, /\badd\b/i);
});
