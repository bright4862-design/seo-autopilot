import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";

import {
  LIMITATION_KINDS,
  LIMITATION_MAX_LENGTH,
  UNSAFE_LIMITATION,
  customerSafeLimitationLine,
  durableScanLimitationKind,
  durableScanStatePresentation,
} from "../../src/lib/durableScanStatePresentation.js";

/**
 * A scan that produced nothing has to say which nothing it produced.
 *
 * The September 6 matrix stopped on sites -- Boudin, Great Jones -- whose runs
 * ended limited for materially different reasons and read identically: "This
 * scan finished with limited evidence", followed by advice to run a fresh scan.
 * A site that is rate-limiting the scanner and a site whose sitemap never
 * answered need different next steps, and telling both owners to retry sends
 * one of them round a loop that cannot terminate.
 *
 * The producer already records the difference in structured codes. These pin
 * the reader to them, and pin the copy to saying nothing the customer must not
 * see.
 */

// ------------------------------------------------------------ the taxonomy --

test("the kind vocabulary is closed", () => {
  // Every branch below claims one of these. A new producer state that maps to
  // nothing must land on unknown_limited rather than inventing a kind the copy
  // table has no entry for.
  assert.deepEqual([...LIMITATION_KINDS].sort(), [
    "access_limited",
    "deadline_reached",
    "rendering_not_verified",
    "save_failed",
    "too_few_usable_pages",
    "unknown_limited",
    "worker_stalled",
  ]);
});

const CASES = [
  {
    name: "Boudin: the site challenged the scanner",
    record: {
      status: "limited",
      evidence_quality_state: "access_limited",
      evidence_quality_reasons: ["access_limited"],
    },
    kind: "access_limited",
  },
  {
    name: "a rate limit reported only as a coverage reason",
    record: {
      status: "limited",
      coverage_state: "access_limited",
      coverage_reasons: ["access_limited"],
    },
    kind: "access_limited",
  },
  {
    name: "Great Jones: URLs found, too few usable HTML pages",
    record: {
      status: "limited",
      evidence_quality_state: "insufficient_discovery",
      evidence_quality_reasons: ["default_route_dominance", "representative_html_pages_below_minimum"],
    },
    kind: "too_few_usable_pages",
  },
  {
    name: "nothing usable came back at all",
    record: {
      status: "limited",
      evidence_quality_state: "no_usable_html",
      evidence_quality_reasons: ["no_usable_html_pages"],
    },
    kind: "too_few_usable_pages",
  },
  {
    name: "the inventory was never established",
    record: {
      status: "limited",
      coverage_state: "inventory_unproven",
      coverage_reasons: ["small_site_inventory_unproven", "no_working_inventory_source"],
    },
    kind: "too_few_usable_pages",
  },
  {
    name: "the crawl ran out of time",
    record: {
      status: "limited",
      coverage_state: "limited_coverage",
      coverage_reasons: ["retained_pages_below_minimum", "coverage_ratio_below_minimum"],
      crawl_timing: { crawl_deadline_reached: true },
    },
    kind: "deadline_reached",
  },
  {
    name: "the whole scan ran out of time",
    record: { status: "limited", scan_deadline_reached: true },
    kind: "deadline_reached",
  },
  {
    name: "pages were fetched but too few could be evaluated",
    record: {
      status: "limited",
      render_evidence: {
        evidence_state: "insufficient_raw_html_evidence",
        coverage: { sufficient: false, reason: "too_few_evaluable_html_pages" },
      },
    },
    kind: "rendering_not_verified",
  },
  {
    name: "the crawl finished and the write did not",
    record: { status: "failed", error_code: "authority_write_failed" },
    kind: "save_failed",
  },
  {
    name: "the worker stopped reporting",
    record: { status: "failed", status_detail: "heartbeat missing; run orphaned" },
    kind: "worker_stalled",
  },
  {
    name: "a limited record carrying no structured reason at all",
    record: { status: "limited" },
    kind: "unknown_limited",
  },
];

/**
 * Rows where exactly one field carries the signal.
 *
 * The cases above are production-shaped and set both a state and a matching
 * reason, which means the reader could drop either channel and still classify
 * them. Real rows are not that generous -- coverage_reasons arrives without
 * coverage_state on limited-v1 records, and discovery_quality_state is
 * sometimes the only field more specific than "insufficient_discovery".
 */
const SOLE_CARRIER = [
  { field: "evidence_quality_state", record: { status: "limited", evidence_quality_state: "access_limited" }, kind: "access_limited" },
  { field: "evidence_quality_reasons", record: { status: "limited", evidence_quality_reasons: ["access_limited"] }, kind: "access_limited" },
  { field: "coverage_state", record: { status: "limited", coverage_state: "access_limited" }, kind: "access_limited" },
  { field: "coverage_reasons", record: { status: "limited", coverage_reasons: ["access_limited"] }, kind: "access_limited" },
  { field: "evidence_quality_state (thin)", record: { status: "limited", evidence_quality_state: "no_usable_html" }, kind: "too_few_usable_pages" },
  { field: "evidence_quality_reasons (thin)", record: { status: "limited", evidence_quality_reasons: ["representative_html_pages_below_minimum"] }, kind: "too_few_usable_pages" },
  { field: "coverage_state (thin)", record: { status: "limited", coverage_state: "limited_coverage" }, kind: "too_few_usable_pages" },
  { field: "coverage_reasons (thin)", record: { status: "limited", coverage_reasons: ["sitemap_never_fetched"] }, kind: "too_few_usable_pages" },
  { field: "discovery_quality_state", record: { status: "limited", discovery_quality_state: "default_route_dominated" }, kind: "too_few_usable_pages" },
  { field: "discovery_quality_state (single page)", record: { status: "limited", discovery_quality_state: "single_page_inventory_unproven" }, kind: "too_few_usable_pages" },
];

for (const { field, record, kind } of SOLE_CARRIER) {
  test(`${field} alone is enough to classify -> ${kind}`, () => {
    assert.equal(durableScanLimitationKind(record), kind);
  });
}

for (const { name, record, kind } of CASES) {
  test(`${name} -> ${kind}`, () => {
    assert.equal(durableScanLimitationKind(record), kind);
    assert.equal(durableScanStatePresentation(record).kind, kind);
  });
}

test("every kind reads differently to a customer", () => {
  // The fault this patch exists to remove: two runs that stopped for different
  // reasons rendering the same paragraph and the same advice.
  const seen = new Map();
  for (const { record, kind } of CASES) {
    const view = durableScanStatePresentation(record);
    const text = `${view.title}|${view.detail}|${view.nextStep}|${view.retryAdvice}`;
    const previous = seen.get(text);
    assert.ok(
      previous === undefined || previous === kind,
      `${kind} is indistinguishable from ${previous}`,
    );
    seen.set(text, kind);
  }
  assert.equal(new Set(seen.values()).size, new Set(CASES.map((entry) => entry.kind)).size);
});

test("a blocked site is not told to try again straight away", () => {
  // Retrying into a rate limit produces another rate limit. The advice has to
  // be tailored to the reason or it is a loop with a confident tone.
  const view = durableScanStatePresentation(CASES[0].record);
  assert.match(view.retryAdvice, /wait/i);
  assert.doesNotMatch(view.retryAdvice, /straight away|right now|immediately/i);
  assert.doesNotMatch(`${view.detail} ${view.retryAdvice}`, /will work|should work|will succeed/i);
});

test("no reason promises that a retry fixes it", () => {
  for (const { record, kind } of CASES) {
    const view = durableScanStatePresentation(record);
    assert.doesNotMatch(
      `${view.detail} ${view.nextStep} ${view.retryAdvice}`,
      /\b(will|should) (work|succeed|fix|complete|finish)\b/i,
      `${kind} promises an outcome it cannot know`,
    );
  }
});

test("a scan that saved nothing never implies it saved something", () => {
  for (const { record, kind } of CASES) {
    const view = durableScanStatePresentation(record);
    assert.equal(typeof view.title, "string");
    assert.ok(view.title.length > 0, `${kind} has no title`);
    assert.ok(view.detail.length > 0, `${kind} has no detail`);
    assert.ok(view.nextStep.length > 0, `${kind} has no next step`);
  }
});

// ------------------------------------------------------- nothing leaks out --

const UNSAFE = [
  "Traceback (most recent call last):\n  File \"/app/scanner.py\", line 42",
  "https://user:hunter2@worker-internal.example.com/run",
  "fixlist-standard150-worker-00042-abc on europe-west1",
  "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaa.bbbb",
  "ConnectionResetError(104, 'Connection reset by peer')",
  "secret f4c3b2a1908d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f",
  "at Object.<anonymous> (/srv/app/index.js:117:9)",
  // Each of these isolates one rule the composite fragments above were
  // masking: the first five all contained a word the keyword rule catches, so
  // the digest, JWT, address, region and stack-position rules were never the
  // reason anything was refused.
  "FixList reviewed pages under run f4c3b2a1908d7e6f5a4b3c2d1e0f9a8b.",
  "FixList reviewed pages with eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaa attached.",
  "FixList reviewed pages and mailed ops@fixlist.example for the rest.",
  "FixList reviewed pages in europe-west1 before stopping.",
  "FixList reviewed pages (/srv/app/index.js:117:9) before stopping.",
  "FixList reviewed pages; ValueError: no usable HTML",
  "FixList reviewed pages listed at //cdn.example.com/inventory.xml",
  "FixList reviewed pages before the token expired.",
  "FixList reviewed pages before the worker stopped.",
];

test("raw failure evidence never reaches the customer", () => {
  for (const fragment of UNSAFE) {
    for (const field of ["status_detail", "error_code", "limitation"]) {
      const view = durableScanStatePresentation({ status: "failed", [field]: fragment });
      const rendered = `${view.title} ${view.detail} ${view.nextStep} ${view.retryAdvice}`;
      assert.doesNotMatch(rendered, /Traceback|Bearer |ConnectionResetError|europe-west1|:\d+:\d+\)/,
        `${field} leaked: ${rendered}`);
      assert.doesNotMatch(rendered, /https?:\/\//, `${field} leaked a URL: ${rendered}`);
      assert.doesNotMatch(rendered, /[0-9a-f]{32}/i, `${field} leaked a token-shaped value`);
      assert.ok(!rendered.includes(fragment), `${field} was echoed verbatim`);
    }
  }
});

test("the limitation line is shown only when it is safe to show", () => {
  // `limitation` is scanner-authored customer copy and is the one field that
  // carries the concrete numbers -- 38 of 3,689 -- that answer whether the
  // saved evidence is worth anything. It is passed through, not paraphrased,
  // so it needs a gate rather than trust.
  assert.equal(
    customerSafeLimitationLine({
      limitation: "FixList reviewed 38 of 3,689 discovered pages, which is too small a share of this site to support an authoritative result.",
    }),
    "FixList reviewed 38 of 3,689 discovered pages, which is too small a share of this site to support an authoritative result.",
  );

  for (const fragment of UNSAFE) {
    assert.equal(customerSafeLimitationLine({ limitation: fragment }), "",
      `an unsafe limitation was published: ${fragment}`);
  }
  assert.equal(customerSafeLimitationLine({}), "");
  assert.equal(customerSafeLimitationLine({ limitation: "   " }), "");
});

test("an over-long limitation is refused rather than cut mid-sentence", () => {
  // Truncation would produce a sentence the scanner never wrote, and the
  // interesting case -- something unbounded got into the field -- is exactly
  // when a half-shown value is least trustworthy.
  //
  // The filler is deliberately plain prose: a run of "a"s is also a run of hex
  // characters, so the digest pattern caught the first version of this fixture
  // and the length bound was never the thing under test.
  const long = `FixList reviewed ${"many pages ".repeat(60)}on this site.`;
  assert.ok(long.length > LIMITATION_MAX_LENGTH);
  assert.equal(customerSafeLimitationLine({ limitation: long }), "");

  const short = long.slice(0, LIMITATION_MAX_LENGTH);
  assert.equal(customerSafeLimitationLine({ limitation: short }), short, "the bound must not reject what fits");
});

test("every pattern in the gate is load-bearing", () => {
  // A gate is only as trustworthy as the reason each of its rules is there. If
  // no fixture is caught by exactly one pattern, that pattern is decoration:
  // it can be deleted without any test noticing, which is how a real one gets
  // deleted next to it. Each rule below must be the sole reason some fixture
  // is refused.
  for (let index = 0; index < UNSAFE_LIMITATION.length; index += 1) {
    const others = UNSAFE_LIMITATION.filter((_, position) => position !== index);
    const uniquelyCaught = UNSAFE.filter((fragment) => (
      UNSAFE_LIMITATION[index].test(fragment) && !others.some((pattern) => pattern.test(fragment))
    ));
    assert.ok(
      uniquelyCaught.length > 0,
      `no fixture needs ${UNSAFE_LIMITATION[index]}; either it is redundant or a fixture is missing`,
    );
  }
});

// ---------------------------------------------- the states that are not it --

test("a running scan is not described as a failure", () => {
  for (const status of ["queued", "crawling", "reviewing"]) {
    const view = durableScanStatePresentation({ status });
    assert.equal(view.kind, "in_progress");
    assert.match(view.title, /still running/i);
    assert.doesNotMatch(view.detail, /failed|couldn't|could not/i);
  }
});

test("a cancelled scan says who stopped it", () => {
  const view = durableScanStatePresentation({ status: "cancelled" });
  assert.equal(view.kind, "cancelled");
  assert.match(view.detail, /stopped/i);
});

test("an empty record does not crash and does not guess", () => {
  for (const record of [undefined, null, {}, { status: "" }, { status: 7 }]) {
    const view = durableScanStatePresentation(record);
    assert.ok(view.title.length > 0);
    assert.ok(view.detail.length > 0);
  }
});

// ------------------------------------------------ the page reads this, not --
// ------------------------------------------------ a copy of its own logic  --

test("FixList renders the shared presentation and holds no second copy", () => {
  // The copy tables used to live in the page. Leaving a duplicate behind is
  // how the two drift, and the page is the one nobody tests.
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

  assert.match(page, /from "@\/lib\/durableScanStatePresentation"/);
  assert.doesNotMatch(page, /function durableFailureKind/);
  assert.doesNotMatch(page, /function getDurableScanStateTitle/);
  assert.doesNotMatch(page, /function getDurableScanStateDetail/);
  assert.match(page, /durableScanStatePresentation\(scanRecord\)/);

  // Both places the scanner's own sentence can appear go through the gate: the
  // note under a readable result, and the limited state that has no result.
  assert.match(page, /customerSafeLimitationLine\(record\)/);
  assert.match(page, /limitation=\{customerSafeLimitationLine\(scanRecord\)\}/);
  assert.doesNotMatch(page, /const limitation = cleanString\(record\?\.limitation\)/);
});

test("the limited state answers all three questions on the page", () => {
  const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  const from = page.indexOf("function RequestedScanState");
  const block = page.slice(from, page.indexOf("\n}", page.indexOf("</div>", from)));

  assert.match(block, /What happened/);
  assert.match(block, /What to do next/);
});
