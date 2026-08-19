import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { repairRowModel } from "../../src/lib/repairPresentation.js";

const rowSource = fs.readFileSync(
  new URL("../../src/components/fixlist/CanonicalRepairRow.jsx", import.meta.url),
  "utf8",
);

test("page-family similarity alone never creates a shared-repair leverage claim", () => {
  const model = repairRowModel({
    id: "pattern-only",
    action_priority: "important",
    page_template_family: "product_page",
    affected_pages: ["/a", "/b", "/c"],
    shared_repair_confirmed: false,
  });

  assert.equal(model.sharedRepairConfirmed, false);
  assert.equal(model.leverage, "");
});

test("explicit shared-repair confirmation may expose bounded multi-page leverage", () => {
  const model = repairRowModel({
    id: "shared",
    action_priority: "important",
    repair_surface: "shared_navigation",
    affected_pages: ["/a", "/b", "/c"],
    shared_repair_confirmed: true,
  });

  assert.equal(model.sharedRepairConfirmed, true);
  assert.equal(model.leverage, "One shared change may improve 3 affected pages");
});

test("single-page repair never receives a shared leverage claim", () => {
  const model = repairRowModel({
    id: "single",
    action_priority: "important",
    affected_pages: ["/a"],
    shared_repair_confirmed: true,
  });

  assert.equal(model.leverage, "");
});

test("compact repair row only renders leverage supplied by the gated presentation model", () => {
  assert.match(rowSource, /model\.leverage/);
  assert.doesNotMatch(rowSource, /shared_repair_confirmed/);
  assert.doesNotMatch(rowSource, /page_template_family/);
});
