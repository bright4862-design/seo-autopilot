import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { evidenceLink } from "../../src/lib/evidenceUrl.js";

const source = await readFile(
  new URL("../../src/pages/FixList.jsx", import.meta.url),
  "utf8",
);

const start = Math.max(
  source.indexOf("function AffectedPage({ page })"),
  source.indexOf("function AffectedPage({ page, websiteUrl, index })"),
);
const end = source.indexOf("function normalizeAffectedPageList", start);
const affectedPageSource = source.slice(start, end);

// The original defect this file guards: a relative affected URL rendered as
// both the label and the line beneath it, so the customer read the same string
// twice. The row now shows a named label and, only when it adds something, the
// host underneath.

test("the second line renders only when it differs from the label", () => {
  assert.ok(start >= 0 && end > start, "AffectedPage moved; this guard must follow it");
  assert.match(
    affectedPageSource,
    /const showHost = link\.isLinkable && cleanString\(host\) !== cleanString\(link\.label\)/,
  );
  assert.match(affectedPageSource, /\{showHost \? <p[^>]*>\{host\}<\/p> : null\}/);
  // Nothing may render a second line unconditionally.
  assert.doesNotMatch(affectedPageSource, /<p[^>]*>\{formatPagePath\((?:resolvedPage|page)\)\}<\/p>/);
});

test("a page with no resolvable origin shows its path once and does not link", () => {
  // This is the case that used to print twice: no origin, so no host line.
  const link = evidenceLink("/menu/lunch", "");
  assert.equal(link.isLinkable, false);
  assert.equal(link.label, "/menu/lunch");
  assert.equal(link.href, "");
});

test("a resolvable page carries a label and a distinct full URL", () => {
  const link = evidenceLink("/menu/lunch", "https://www.ikessandwich.com");
  assert.equal(link.label, "/menu/lunch");
  assert.equal(link.title, "https://www.ikessandwich.com/menu/lunch");
  assert.notEqual(link.label, link.title, "the two lines must not be the same string");
});

test("the affected-page row links the label itself, not only an icon", () => {
  // The audit found evidence URLs rendered as plain text. The label is now an
  // anchor, and every anchor opens safely in a new tab.
  const anchors = affectedPageSource.match(/<a\b[^>]*>/gs) || [];
  assert.ok(anchors.length >= 2, `expected the label and the icon to be links, saw ${anchors.length}`);
  for (const anchor of anchors) {
    assert.match(anchor, /target="_blank"/, anchor);
    assert.match(anchor, /rel="noopener noreferrer"/, anchor);
    assert.match(anchor, /aria-label=\{link\.linkName\}/, anchor);
  }
});

test("a link is rendered only when the shared contract says it is safe", () => {
  assert.match(affectedPageSource, /\{link\.isLinkable \?/);
  assert.doesNotMatch(affectedPageSource, /href=\{page\}/, "the raw page value must never become an href");
});
