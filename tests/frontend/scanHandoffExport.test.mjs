import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { buildRepairCards } from "../../src/lib/repairCardModel.js";
import {
  HANDOFF_INSTRUCTIONS,
  SCAN_HANDOFF_SCHEMA,
  buildScanHandoff,
  scanHandoffFilename,
  serializeScanHandoff,
} from "../../src/lib/scanHandoff.js";

/**
 * The FixList is the product, and until this export existed it lived only on
 * one screen. A customer who wanted an assistant to walk them through it had to
 * retype it; a customer who wanted their web person to do the work had nothing
 * to send.
 *
 * The risk an export carries is that it drifts from the page -- a different
 * count, a score the page refused to show, a page URL nobody can open -- so
 * every assertion here is about the file agreeing with the screen.
 */

const SCAN = {
  scan_id: "6a9a9b3f2a9c1f80a7b529ce",
  website_url: "https://example-tours.com",
  created_at: "2026-09-04T10:20:45Z",
};

/**
 * Every leaf in the export paired with the field name holding it, so a check can
 * compare values rather than characters and still say which field it means.
 */
function exportedFields(node, key = "", found = []) {
  if (Array.isArray(node)) node.forEach((entry) => exportedFields(entry, key, found));
  else if (node && typeof node === "object") {
    Object.entries(node).forEach(([name, entry]) => exportedFields(entry, name, found));
  } else found.push([key, node]);
  return found;
}

function row(fixId, fingerprint, pages, overrides = {}) {
  return {
    id: fixId,
    fix_id: fixId,
    rule: "missing_meta_description",
    repair_fingerprint: fingerprint,
    status: "needs_approval",
    priority: "high",
    issue_title: "Add a meta description",
    why_it_matters: "Searchers need a useful summary.",
    recommendation: "Add one page-specific description.",
    affected_pages: pages,
    page_count: pages.length,
    ...overrides,
  };
}

test("the export lists one fix per customer action, exactly as the page does", () => {
  // Two scanner rows sharing a repair fingerprint are one thing to do, and the
  // page merges them into one card. An export that counted rows instead would
  // tell an assistant to walk the owner through the same repair twice.
  const issues = [
    row("first", "shared-template", ["/fr/tours"]),
    row("second", "shared-template", ["/de/tours"]),
    row("third", "image-alt", ["/gallery"], { rule: "image_alt_text", priority: "medium" }),
  ];
  const cards = buildRepairCards(issues);
  const handoff = buildScanHandoff({ scanRecord: SCAN, cards });

  assert.equal(cards.length, 2, "the page renders two merged actions");
  assert.equal(handoff.fix_count, cards.length);
  assert.equal(handoff.fixes.length, cards.length);
  assert.deepEqual(
    handoff.fixes.map((fix) => fix.title),
    cards.map((card) => card.title),
    "the exported fixes are the rendered cards, in the rendered order",
  );
  assert.deepEqual(handoff.fixes.map((fix) => fix.n), [1, 2], "fixes are numbered for an assistant to work through");
});

test("a score the page could not measure is never exported as a number", () => {
  // ScoreRing renders "unavailable" rather than a figure when the scan could
  // not verify enough usable pages. Exporting any number there hands an
  // assistant something to reason about that nobody measured -- and a model
  // asked to explain a 62 will happily explain a 62.
  const handoff = buildScanHandoff({
    scanRecord: SCAN,
    cards: buildRepairCards([row("only", "fp", ["/"])]),
    healthScore: 62,
    scoreUnavailable: true,
  });

  assert.equal(handoff.health_score, null);
  assert.equal(handoff.health_score_available, false);

  // Read as score fields, not as text and not as bare values.
  //
  // Sweeping the serialized string for "62" also matched the millisecond field
  // of `generated_at`, which defaults to the current time, so the check failed
  // on about one run in sixty against a document whose score was correctly
  // null. Rejecting the value 62 anywhere trades that for a different false
  // positive: `pages_affected`, `pages_found` and `fix_count` are all free to
  // be 62 on a real site, and a correct export of one would fail.
  //
  // Every field whose name carries the score is checked, at any depth, so a
  // leak into a nested or renamed score field is still caught.
  const scoreFields = exportedFields(handoff).filter(([key]) => /score/i.test(key));
  assert.ok(scoreFields.length > 0, "the export must carry score fields for this to mean anything");
  assert.ok(
    !scoreFields.some(([, value]) => value === 62 || value === "62"),
    `an unavailable score must not survive in any score field: ${JSON.stringify(scoreFields)}`,
  );
});

test("a measured score is exported as a number, not a string", () => {
  const handoff = buildScanHandoff({
    scanRecord: SCAN,
    cards: buildRepairCards([row("only", "fp", ["/"])]),
    healthScore: "72",
  });

  assert.equal(handoff.health_score, 72);
  assert.equal(typeof handoff.health_score, "number");
  assert.equal(handoff.health_score_available, true);
});

test("the real affected-page total is exported even when the sample is capped", () => {
  // A saved result keeps a bounded page list while page_count carries the total
  // the scan actually proved. Exporting the list length as the total would tell
  // an owner ten pages need fixing when the scan found ninety.
  const pages = Array.from({ length: 24 }, (_, index) => `/tour/${index + 1}`);
  const cards = buildRepairCards([row("wide", "fp", pages, { page_count: 90 })]);
  const [fix] = buildScanHandoff({ scanRecord: SCAN, cards }).fixes;

  assert.equal(fix.pages_affected, 90);
  assert.equal(fix.example_pages.length, 10, "the sample stays small enough to paste into a chat");
  assert.equal(fix.example_pages_are_partial, true);
});

test("a fix whose pages are all listed is not marked as a partial sample", () => {
  const cards = buildRepairCards([row("narrow", "fp", ["/a", "/b"])]);
  const [fix] = buildScanHandoff({ scanRecord: SCAN, cards }).fixes;

  assert.equal(fix.pages_affected, 2);
  assert.deepEqual(fix.example_pages, ["https://example-tours.com/a", "https://example-tours.com/b"]);
  assert.equal(fix.example_pages_are_partial, false);
});

test("example pages are absolute URLs the owner can open", () => {
  // The scan stores site-relative paths. An assistant told to "check /fr/tours"
  // cannot open it, and neither can the owner reading the conversation.
  const cards = buildRepairCards([row("paths", "fp", ["/fr/tours", "/de/tours"])]);
  const [fix] = buildScanHandoff({ scanRecord: SCAN, cards }).fixes;

  for (const page of fix.example_pages) {
    assert.match(page, /^https:\/\/example-tours\.com\//, `${page} must be openable`);
  }
});

test("a long fix list is truncated and says so", () => {
  const issues = Array.from({ length: 63 }, (_, index) => row(`fix-${index}`, `fp-${index}`, [`/page-${index}`]));
  const cards = buildRepairCards(issues);
  const handoff = buildScanHandoff({ scanRecord: SCAN, cards });

  assert.equal(cards.length, 63);
  assert.equal(handoff.fixes.length, 50);
  assert.equal(handoff.fix_count, handoff.fixes.length, "the stated count must match what is in the file");
  assert.equal(handoff.fix_count_is_partial, true);
});

test("a complete fix list is not flagged as truncated", () => {
  const cards = buildRepairCards([row("one", "fp-1", ["/a"]), row("two", "fp-2", ["/b"])]);
  const handoff = buildScanHandoff({ scanRecord: SCAN, cards });

  assert.equal(handoff.fix_count, 2);
  assert.equal(handoff.fix_count_is_partial, false);
});

test("what the scan could not see travels with what it found", () => {
  // A Standard 150 scan checks a sample of a larger site. Without the
  // limitation an assistant reads "17 fixes" as the complete state of the site
  // and answers for pages nobody looked at.
  const handoff = buildScanHandoff({
    scanRecord: SCAN,
    cards: buildRepairCards([row("only", "fp", ["/"])]),
    pagesScanned: 150,
    pagesFound: 5000,
    limitations: ["  Checked 150 of 5,000 pages.  ", "", null, "Sitemap was unreachable."],
  });

  assert.equal(handoff.pages_checked, 150);
  assert.equal(handoff.pages_found, 5000);
  assert.deepEqual(handoff.limitations, ["Checked 150 of 5,000 pages.", "Sitemap was unreachable."]);
});

test("no more than five limitations are carried", () => {
  const handoff = buildScanHandoff({
    scanRecord: SCAN,
    cards: [],
    limitations: Array.from({ length: 9 }, (_, index) => `Limitation ${index}`),
  });

  assert.equal(handoff.limitations.length, 5);
});

test("the file tells the assistant to walk the owner through it, not summarize it", () => {
  const handoff = buildScanHandoff({ scanRecord: SCAN, cards: [] });

  assert.equal(handoff.schema, SCAN_HANDOFF_SCHEMA);
  assert.equal(handoff.how_to_use, HANDOFF_INSTRUCTIONS);
  assert.match(HANDOFF_INSTRUCTIONS, /one at a time/);
  assert.match(HANDOFF_INSTRUCTIONS, /Do not invent issues/);
  assert.match(HANDOFF_INSTRUCTIONS, /pages that were not scanned/);
});

test("the serialized file is valid JSON an assistant can read back", () => {
  const handoff = buildScanHandoff({
    scanRecord: SCAN,
    cards: buildRepairCards([row("only", "fp", ["/fr/tours"])]),
    summary: 'A "quoted" summary with — punctuation.',
  });
  const text = serializeScanHandoff(handoff);

  assert.deepEqual(JSON.parse(text), handoff);
  assert.ok(text.endsWith("\n"), "the file ends with a newline like every other text export");
  assert.ok(text.includes("\n  "), "the file is indented so a person can read it too");
});

test("the export stays small enough to paste into a chat", () => {
  // The saved scan record keeps up to 150 pages at roughly forty fields each.
  // Shipping that would bury the handful of things the owner has to do, and a
  // context window is exactly where the cost lands.
  const issues = Array.from({ length: 40 }, (_, index) => row(
    `fix-${index}`,
    `fp-${index}`,
    Array.from({ length: 60 }, (_, page) => `/section-${index}/page-${page}`),
    { page_count: 60 },
  ));
  const handoff = buildScanHandoff({ scanRecord: SCAN, cards: buildRepairCards(issues) });
  const bytes = Buffer.byteLength(serializeScanHandoff(handoff), "utf8");

  assert.equal(handoff.fixes.length, 40);
  assert.ok(bytes < 60_000, `a forty-fix export grew to ${bytes} bytes`);
});

test("the filename names the site and the scan day and is safe to save", () => {
  const name = scanHandoffFilename(SCAN);

  assert.equal(name, "fixlist-example-tours-com-2026-09-04.json");
  assert.doesNotMatch(name, /[/\\\s:]/, "a filename with a separator or space is not safe to save");
});

test("a record with no site or date still produces a usable filename", () => {
  const name = scanHandoffFilename({});

  assert.match(name, /^fixlist-scan-\d{4}-\d{2}-\d{2}\.json$/);
});

/**
 * The wiring half. `exportScanReportPdf` sat in the tree for months with no
 * call site anywhere, and `download_json_enabled: true` was written into every
 * scan's debug record by a page that had no download. Both read as shipped
 * features. These assertions are what stops that from happening again.
 */
const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

test("the FixList page actually renders the export control", () => {
  assert.match(page, /import \{ buildScanHandoff, scanHandoffFilename, serializeScanHandoff \} from "@\/lib\/scanHandoff"/);
  assert.match(page, /function ScanExportControls\(/);
  assert.match(page, /<ScanExportControls\b/, "the component must be rendered, not merely defined");
});

test("the export is built from the cards the page renders", () => {
  // The one failure this whole feature can produce that a customer would not
  // catch is a file describing a different scan than the screen above it.
  //
  // The props are read out of the element itself rather than matched across the
  // file: `cards={customerRepairCards}` also appears on the list component
  // below, so an unbounded match would pass on a control wired to anything.
  const start = page.indexOf("<ScanExportControls");
  const element = page.slice(start, page.indexOf("/>", start) + 2);
  assert.ok(start > -1 && element.length > 0, "the export control must be rendered");

  assert.match(element, /\bcards=\{customerRepairCards\}/);
  assert.match(element, /\bissues=\{active\}/);
  assert.match(element, /\bscanRecord=\{scanRecord\}/);
  assert.match(element, /\bhealthScore=\{healthScore\}/);
  assert.match(element, /\bscoreUnavailable=\{scoreUnavailable\}/);
});

test("the export is offered only where the page shows canonical repair cards", () => {
  // A legacy or unsupported saved scan renders through a different path, and
  // the page says outright it cannot safely display one. Exporting from it
  // would hand an assistant a list the page itself refuses to stand behind.
  assert.match(
    page,
    /\{repairPresentation\.canonical === true && customerRepairCards\.length > 0 \? \(\s*<ScanExportControls/,
  );
});

test("the PDF writer is fetched on demand, not shipped to every reader", () => {
  // jsPDF is the largest dependency in the bundle and only this one control
  // needs it. A static import would put it in front of every FixList reader,
  // including the ones who never export anything.
  assert.match(page, /await import\("@\/lib\/exportScanReport"\)/);
  assert.doesNotMatch(page, /^import .*from "@\/lib\/exportScanReport"/m);
  assert.doesNotMatch(page, /from "jspdf"/);
});

test("the PDF is never handed a score the page called unavailable", () => {
  assert.match(page, /seo_score: scoreUnavailable \? null : healthScore/);
});

test("every export emits the analytics event the admin report already counts", () => {
  // report_exported has been a registered category with no emitter, so the
  // admin tile has always read zero. Each of the three controls records one.
  assert.match(page, /import \{ trackEvent \} from "@\/lib\/analytics"/);
  assert.match(page, /trackEvent\("report_exported"/);
  for (const format of ['"json"', '"json_clipboard"', '"pdf"']) {
    assert.match(page, new RegExp(`recordExport\\(${format}`), `the ${format} export must be recorded`);
  }
});

test("a failed export tells the customer, and never silently does nothing", () => {
  // Downloads and clipboard writes both fail in real browsers -- a blocked
  // popup, a denied clipboard permission, a PDF library that will not load.
  // A control that appears to do nothing is worse than one that says why.
  const component = page.slice(page.indexOf("function ScanExportControls("), page.indexOf("function CustomerRepairList("));
  assert.ok(component.length > 0, "the export component must exist");
  assert.equal((component.match(/setFailure\("[^"]/g) || []).length, 3, "each control reports its own failure");
  assert.match(component, /\{failure \? \(/, "the failure must be rendered, not only stored");
});
