import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { transform } from "esbuild";
import { repairRolePresentation } from "../../src/lib/repairRolePresentation.js";

const url = new URL("../../src/components/fixlist/RepairRoleView.jsx", import.meta.url);
let source = await readFile(url, "utf8");
for (const file of ["repairRoleExplanations.js", "repairRolePresentation.js"]) {
  source = source.replace(`"../../lib/${file}"`, JSON.stringify(new URL(`../../src/lib/${file}`, import.meta.url).href));
}
const compiled = await transform(source, { loader: "jsx", jsxFactory: "React.createElement", format: "esm" });
const code = `import React from ${JSON.stringify(import.meta.resolve("react"))};\n${compiled.code}`;
const { RepairRoleSelector, RepairRoleExplanation } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const repair = { fix_id: "one", rule: "missing_h1", recommendation: "Use the existing page title field for the main heading.", action_priority: "fix_first", affected_pages: ["/one"] };

for (const role of ["owner", "marketing", "seo", "developer"]) {
  test(`${role} explanation leaves scanner instructions and source data intact`, () => {
    const input = structuredClone(repair);
    const before = structuredClone(input);
    const html = render(RepairRoleExplanation, { repair: input, role });
    assert.ok(html.includes(renderToStaticMarkup(React.createElement(React.Fragment, null, repairRolePresentation(input, role).explanation.explanation))));
    assert.ok(html.includes(repair.recommendation));
    assert.deepEqual(input, before);
    assert.match(render(RepairRoleSelector, { role, onRoleChange() {} }), new RegExp(`value="${role}" selected=""`));
  });
}

function selectElement(props) {
  const label = RepairRoleSelector(props);
  assert.equal(label.type, "label");
  return React.Children.toArray(label.props.children).find((child) => child?.type === "select");
}

test("selector emits only a valid role and waits for the parent to update its controlled value", () => {
  const changes = [];
  const select = selectElement({ role: "owner", onRoleChange: (value) => changes.push(value) });
  select.props.onChange({ target: { value: "developer" } });
  select.props.onChange({ target: { value: "invented" } });
  assert.deepEqual(changes, ["developer"]);
  assert.equal(select.props.value, "owner");
});

test("disabled or read-only selector does not invoke a change", () => {
  const select = selectElement({ role: "seo", disabled: true, onRoleChange() { assert.fail("disabled"); } });
  select.props.onChange({ target: { value: "owner" } });
  assert.equal(select.props.disabled, true);
  assert.equal(selectElement({ role: "owner" }).props.disabled, true);
});

test("unsupported role uses the existing fallback while retaining scanner remediation", () => {
  const html = render(RepairRoleExplanation, { repair, role: "unknown" });
  assert.ok(html.includes(repairRolePresentation(repair, "unknown").explanation.explanation));
  assert.ok(html.includes(repair.recommendation));
  assert.match(render(RepairRoleSelector, { role: "unknown", onRoleChange() {} }), /Choose a role/);
});

test("unknown rule stays on the manual-review fallback", () => {
  const item = { rule: "unmapped_future_rule" };
  assert.ok(render(RepairRoleExplanation, { repair: item }).includes(repairRolePresentation(item, "owner").suggestion.suggestedFix));
});

test("missing repair renders nothing and scanner strings are escaped", () => {
  assert.equal(render(RepairRoleExplanation, {}), "");
  const html = render(RepairRoleExplanation, { repair: { ...repair, recommendation: "<script>alert(1)</script>" } });
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});
