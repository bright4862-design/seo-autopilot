import assert from "node:assert/strict";
import test from "node:test";
import { pageCapFromRecord, inventoryCoverageLine, serverSelectedPriorityCards } from "../../src/lib/scanPresentation.js";
import { scanProgressModel } from "../../src/lib/scanProgressPresentation.js";
import { resolveScanFunctionRoute } from "../../src/lib/scanFunctionRouting.js";
import { buildRepairCard, whereLine } from "../../src/lib/repairCardModel.js";

test("the saved cap controls presentation while historical scans keep their cap", () => {
  assert.equal(pageCapFromRecord({}), 150);
  assert.equal(pageCapFromRecord({ scan_mode: "deep" }), 85);
  assert.equal(pageCapFromRecord({ scan_mode: "standard_500", page_cap: 500 }), 500);
  assert.equal(pageCapFromRecord({ page_cap: 9000 }), 150);
  assert.equal(pageCapFromRecord({ page_cap: -10 }), 150);
  assert.equal(pageCapFromRecord({ page_cap: "500" }), 150);
});

test("committed staged plan supplies the progress denominator", () => {
  const progress = scanProgressModel({ status: "crawling", pages_crawled: 100, pages_planned: 500, pages_found: 5000 });
  assert.equal(progress.totalPages, 500);
  assert.equal(progress.percent, 20);
  assert.equal(progress.countLabel, "100 of 500 pages checked");
  assert.equal(scanProgressModel({ status: "queued", pages_planned: 0 }).determinate, false);
  assert.equal(scanProgressModel({ status: "crawling", pages_planned: -1 }).determinate, false);
});

test("limited results are terminal and do not pretend the whole plan was checked", () => {
  const model = scanProgressModel({ status: "limited", pages_crawled: 67, pages_planned: 500 });
  assert.equal(model.terminal, true);
  assert.equal(model.active, false);
  assert.equal(model.percent, 13);
  assert.equal(model.phaseLabel, "Scan finished with limited evidence");
});

test("capped inventory is described as a lower bound, with no inferred section count", () => {
  assert.equal(inventoryCoverageLine({ pages_crawled: 150, pages_found: 5000, inventory_capped: true }), "We checked 150 pages out of at least 5,000 found.");
  assert.equal(inventoryCoverageLine({ pages_crawled: 150, pages_found: 5000 }), "We checked 150 pages out of 5,000 found.");
});

test("priority cards follow only the server shortlist and preserve all other cards", () => {
  const cards = ["a", "b", "c", "d"].map(id => ({ evidence: { mergedFromFixIds: [id] }, title: id }));
  const result = serverSelectedPriorityCards(cards, ["c", "a"]);
  assert.deepEqual(result.first.map(card => card.title), ["c", "a"]);
  assert.deepEqual(result.remaining.map(card => card.title), ["b", "d"]);
  assert.equal(serverSelectedPriorityCards(cards, undefined), null);
  assert.equal(serverSelectedPriorityCards(cards, ["unknown"]), null);
  assert.equal(serverSelectedPriorityCards(cards, ["a", "a"]), null);
  assert.equal(serverSelectedPriorityCards(cards, ["a", "b", "c", "d"]), null);
});

test("V9 routing is an explicit deployment opt-in for admission, read and delete together", () => {
  for (const name of ["startStandardScanJob", "getCustomerScanResult", "deleteCustomerScanData"]) {
    assert.equal(resolveScanFunctionRoute(`${name}V8`), `${name}V8`);
    assert.equal(resolveScanFunctionRoute(`${name}V8`, "V9"), `${name}V9`);
    assert.equal(resolveScanFunctionRoute(`${name}V8`, "v9"), `${name}V8`);
  }
  assert.equal(resolveScanFunctionRoute("createAccessCheckout", "V9"), "createAccessCheckout");
});

test("Stage3 rows retain their direct identity for the server shortlist", () => {
  const cards = [{ fixId: "fix-row", evidence: { mergedFromFixIds: [] } }];
  assert.equal(serverSelectedPriorityCards(cards, ["fix-row"]).first[0], cards[0]);
});

test("incomplete affected counts remain lower bounds through card normalization", () => {
  const raw = { fix_id: "bounded", rule: "missing_h1", page_count: 150, affected_page_count: 475, affected_page_count_is_lower_bound: true, affected_pages: ["/a"] };
  assert.equal(whereLine(raw), "At least 475 pages on your site.");
  const card = buildRepairCard({ pageCount: 150, original: raw });
  assert.equal(card.evidence.pageCount, 475);
  assert.equal(card.evidence.pageCountIsLowerBound, true);
  assert.equal(card.where, "At least 475 pages on your site.");
  assert.equal(whereLine({ ...raw, affected_page_count_is_lower_bound: false }), "475 pages on your site.");
});

test("template extrapolation requires explicit agreement and inventory evidence", () => {
  const estimate = { route_pattern: "/products/:slug", checked_sample_count: 12, observed_affected_count: 12, inventory_count: 1560, estimated_affected_page_count: 1560, is_extrapolation: true, qualification: "Seen on 12 of 12 sampled pages; 1,560 URLs of this type were found." };
  assert.deepEqual(buildRepairCard({ template_impact_estimates: [estimate] }).templateImpactEstimates, [estimate]);
  assert.equal(buildRepairCard({ template_impact_estimates: [{ ...estimate, is_extrapolation: false }] }).templateImpactEstimates, undefined);
  assert.equal(buildRepairCard({ template_impact_estimates: [{ ...estimate, observed_affected_count: 11 }] }).templateImpactEstimates, undefined);
});
