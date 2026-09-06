import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { focusedPathSections } from "../../src/lib/focusedScanScope.js";
import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV2/authoritySnapshot.js";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV2/projection.js";

/**
 * The September 6 production matrix stopped on this.
 *
 * Four sites showed section rows totalling 148 "sampled" against 39 or 40 pages
 * actually checked. `sampling_report()` builds those prefix counts from the URLs
 * chosen before the crawl, so the number measures an intention; the page
 * labelled it "sampled" and "represented", which a customer reads as an
 * observation. FixList was overstating the evidence it held.
 *
 * The producer now records both: what was selected, and what the crawl actually
 * returned. These pin the consumer to the second one, and pin legacy records --
 * which only ever carried selection -- to saying so.
 */

const MATRIX = [
  { site: "Salt & Straw", found: 345, checked: 39, selected: { "/products": 54, "/collections": 29, "/blogs": 35, "/pages": 30 }, checkedBy: { "/products": 12, "/collections": 9, "/blogs": 8, "/pages": 7 } },
  { site: "Stumptown Coffee", found: 301, checked: 39, selected: { "/products": 18, "/collections": 45, "/blogs": 55, "/pages": 30 }, checkedBy: { "/products": 6, "/collections": 11, "/blogs": 13, "/pages": 6 } },
  { site: "Fly By Jing", found: 324, checked: 40, selected: { "/products": 80, "/collections": 32, "/blogs": 24, "/pages": 12 }, checkedBy: { "/products": 19, "/collections": 8, "/blogs": 6, "/pages": 4 } },
  { site: "Fishwife", found: 318, checked: 40, selected: { "/products": 80, "/collections": 32, "/blogs": 24, "/pages": 12 }, checkedBy: { "/products": 17, "/collections": 9, "/blogs": 7, "/pages": 5 } },
];

const DISCOVERED = { "/products": 120, "/collections": 60, "/blogs": 48, "/pages": 30 };

function record({ found, checked, selected, checkedBy }, { legacy = false } = {}) {
  const evidence = {
    sitemap_urls_discovered: found,
    path_prefixes_discovered: DISCOVERED,
    // A legacy record carries only the pre-crawl selection, under its old name.
    ...(legacy
      ? { path_prefixes_sampled: selected, sitemap_urls_sampled: 148 }
      : {
        path_prefixes_selected: selected,
        sitemap_urls_selected: 148,
        path_prefixes_checked: checkedBy,
        pages_checked: checked,
      }),
  };
  return { website_url: "https://x.com", pages_found: found, pages_crawled: checked, sampling_evidence: evidence };
}

test("no section may claim more checked pages than the crawl returned", () => {
  // The invariant the matrix broke: 54 + 29 + 35 + 30 = 148 against 39 checked.
  for (const site of MATRIX) {
    const sections = focusedPathSections(record(site));
    const total = sections.reduce((sum, row) => sum + (row.checked || 0), 0);
    assert.ok(
      total <= site.checked,
      `${site.site}: sections claim ${total} checked against ${site.checked} pages crawled`,
    );
  }
});

test("selected and checked are reported as different numbers", () => {
  for (const site of MATRIX) {
    const sections = focusedPathSections(record(site));
    assert.ok(sections.length > 0, `${site.site}: expected section rows`);
    for (const row of sections) {
      assert.ok(row.selected > row.checked, `${site.site} ${row.requested_path_prefix}: ${row.selected} vs ${row.checked}`);
    }
  }
});

test("a record with checked evidence says its coverage is measured", () => {
  const [row] = focusedPathSections(record(MATRIX[0]));

  assert.equal(row.coverageEvidence, "checked");
  assert.equal(typeof row.checked, "number");
  assert.equal(typeof row.checkedCoverage, "number");
  assert.ok(row.checkedCoverage > 0 && row.checkedCoverage <= 1);
});

test("a legacy record exposes selection only, and never a coverage figure", () => {
  // These records were written before the crawl recorded outcomes. Nothing in
  // them can support a percentage, and presenting one would reproduce the exact
  // overstatement this change exists to remove.
  const sections = focusedPathSections(record(MATRIX[0], { legacy: true }));
  assert.ok(sections.length > 0, "legacy rows must still render");

  for (const row of sections) {
    assert.equal(row.coverageEvidence, "selected_only");
    assert.equal(row.checked, null, "a legacy record cannot know what was checked");
    assert.equal(row.checkedCoverage, null, "no percentage may be derived from selection");
    assert.ok(row.selected > 0, "the selection count is still real and still shown");
  }
});

test("legacy rows keep a deterministic order rather than ranking by selection", () => {
  // Selection is not a proxy for successful coverage: a prefix can be heavily
  // selected and barely fetched. Ordering by it would recommend the wrong
  // follow-up scan while looking authoritative.
  const sections = focusedPathSections(record(MATRIX[0], { legacy: true }));
  const discovered = sections.map((row) => row.discovered);
  assert.deepEqual(discovered, [...discovered].sort((a, b) => b - a), "legacy order is by discovered size");
});

test("checked rows are ranked by measured coverage, worst first", () => {
  // Deliberately inverted: the largest section is the best covered and the
  // smallest the worst, so ranking by coverage and ranking by discovered size
  // give opposite answers. The production fixtures happen to agree on both, and
  // a test built only from those passes with the sort removed entirely.
  const inverted = {
    ...MATRIX[0],
    checkedBy: { "/products": 60, "/collections": 12, "/blogs": 6, "/pages": 1 },
  };
  const sections = focusedPathSections(record(inverted));
  const coverage = sections.map((row) => row.checkedCoverage);

  assert.deepEqual(coverage, [...coverage].sort((a, b) => a - b), "least-covered section is recommended first");
  assert.equal(sections[0].requested_path_prefix, "/pages", "the worst-covered folder leads");
  assert.equal(sections.at(-1).requested_path_prefix, "/products", "the best-covered folder is last");
  assert.notDeepEqual(
    sections.map((row) => row.discovered),
    [...sections.map((row) => row.discovered)].sort((a, b) => b - a),
    "this fixture must not be orderable by discovered size, or it proves nothing",
  );
});

test("a checked count of zero is a real answer, not a missing one", () => {
  // A section discovered but never reached must read as nothing checked, not as
  // unknown, or the customer cannot tell an unscanned folder from a legacy record.
  const site = { ...MATRIX[0], checkedBy: { "/products": 12, "/collections": 0, "/blogs": 8, "/pages": 7 } };
  const sections = focusedPathSections(record(site));
  const collections = sections.find((row) => row.requested_path_prefix === "/collections");

  assert.equal(collections.checked, 0);
  assert.equal(collections.checkedCoverage, 0);
  assert.equal(collections.coverageEvidence, "checked");
});


test("checked coverage survives the seal and the customer projection", () => {
  // The section rows are only as honest as the field that reaches them. A
  // value the producer records and the persistence layer drops would leave the
  // page falling back to selection -- the exact bug -- while every unit test
  // above still passed.
  const evidence = {
    sampling_version: "balanced_sitemap_buckets_v6_selected_and_checked_split",
    sitemap_urls_discovered: 345,
    sitemap_urls_selected: 148,
    path_prefixes_discovered: DISCOVERED,
    path_prefixes_selected: MATRIX[0].selected,
    path_prefixes_checked: MATRIX[0].checkedBy,
    pages_checked: 39,
  };

  const snapshot = buildAuthoritySnapshot({
    scan: { scan_id: "s1", website_url: "https://x.com", status: "complete", pages_found: 345, pages_crawled: 39, sampling_evidence: evidence },
    review: {},
    identity: {},
    userId: "u1",
  });
  assert.deepEqual(
    snapshot.scan.sampling_evidence.path_prefixes_checked,
    MATRIX[0].checkedBy,
    "the authority snapshot dropped the checked coverage it is meant to seal",
  );
  assert.equal(snapshot.scan.sampling_evidence.pages_checked, 39);

  const projected = buildCustomerProjection({
    run: { id: "s1", scan_id: "s1", website_url: "https://x.com", status: "complete", pages_found: 345, pages_crawled: 39, sampling_evidence: evidence },
    fixList: { id: "f1" },
    fixItems: [],
    fullAccess: true,
    authorityVerified: true,
    resultIntegrityVerified: true,
  });
  // The projection nests the scan under `run`, and that is the object the page
  // is handed -- so this is the shape the assertion has to walk, not a
  // convenient flattening of it.
  assert.deepEqual(projected.run.sampling_evidence.path_prefixes_checked, MATRIX[0].checkedBy);

  // And the page reads it from exactly that projected shape.
  const [row] = focusedPathSections(projected.run);
  assert.equal(row.coverageEvidence, "checked");
  assert.ok(row.checked > 0);
});

test("the section rows never say sampled or represented again", () => {
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  const from = page.indexOf("Sections to scan next");
  // Comments are stripped first: the one above this copy quotes the old
  // wording on purpose, to record what the numbers used to claim.
  const block = page
    .slice(from, page.indexOf("Scan this section separately", from))
    .replace(/\/\/.*$/gm, "")
    .replace(/\/\*[\s\S]*?\*\//g, "");

  assert.doesNotMatch(block, /\bsampled\b/i, "both words read as an observation the scan did not make");
  assert.doesNotMatch(block, /\brepresented\b/i);
  assert.match(block, /checked here/);
  assert.match(block, /chosen for this scan/, "a selection-only record must say so");
  assert.match(block, /section\.coverageEvidence === "checked"/, "the percentage is gated on real evidence");
});
