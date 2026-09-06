import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  evidenceDisplayLabel,
  evidenceLink,
  evidenceLinkName,
  evidencePath,
  isAbsoluteHttpUrl,
  resolveEvidenceUrl,
} from "../../src/lib/evidenceUrl.js";

const SITE = "https://www.ikessandwich.com";

test("the site root is named, not shown as a bare slash", () => {
  // The audit's finding: "/" tells a customer nothing about which page is meant.
  assert.equal(evidenceDisplayLabel(`${SITE}/`), "Homepage (/)");
  assert.equal(evidenceDisplayLabel("/"), "Homepage (/)");
  assert.equal(evidenceDisplayLabel(""), "Homepage (/)");
});

test("any other page reads as the path someone editing the site recognises", () => {
  assert.equal(evidenceDisplayLabel(`${SITE}/menu/lunch`), "/menu/lunch");
  assert.equal(evidenceDisplayLabel("/locations/austin"), "/locations/austin");
  assert.equal(evidenceDisplayLabel(`${SITE}/search?q=tuna`), "/search?q=tuna");
});

test("a relative path resolves against the scanned origin, never the app host", () => {
  assert.equal(resolveEvidenceUrl("/menu/", SITE), `${SITE}/menu/`);
  // With no trustworthy origin there is no honest absolute URL to show, so the
  // contract refuses rather than inventing one against whatever host is serving.
  assert.equal(resolveEvidenceUrl("/menu/", ""), "");
  assert.equal(resolveEvidenceUrl("/menu/", "not-a-url"), "");
});

test("an absolute URL is preserved exactly", () => {
  assert.equal(resolveEvidenceUrl(`${SITE}/menu/`, SITE), `${SITE}/menu/`);
  assert.equal(resolveEvidenceUrl("https://other.example/x", SITE), "https://other.example/x");
});

test("an unsafe scheme never becomes a clickable link", () => {
  for (const hostile of [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "mailto:someone@example.com",
    "tel:+15551234",
  ]) {
    assert.equal(resolveEvidenceUrl(hostile, SITE), "", `${hostile} produced an href`);
    assert.equal(evidenceLink(hostile, SITE).isLinkable, false, `${hostile} was linkable`);
    assert.equal(evidenceLink(hostile, SITE).href, "", `${hostile} kept an href`);
  }
});

test("isAbsoluteHttpUrl accepts only http and https", () => {
  assert.equal(isAbsoluteHttpUrl("https://a.example/"), true);
  assert.equal(isAbsoluteHttpUrl("http://a.example/"), true);
  assert.equal(isAbsoluteHttpUrl("//a.example/"), false);
  assert.equal(isAbsoluteHttpUrl("/menu"), false);
  assert.equal(isAbsoluteHttpUrl("javascript:alert(1)"), false);
});

test("the path is shown without the origin", () => {
  assert.equal(evidencePath(`${SITE}/menu/lunch`), "/menu/lunch");
  assert.equal(evidencePath(`${SITE}/`), "/");
  assert.equal(evidencePath("/menu/lunch"), "/menu/lunch");
});

test("the accessible name says what opening the link does", () => {
  assert.equal(evidenceLinkName(`${SITE}/`), "Open affected page: Homepage (/)");
  assert.equal(evidenceLinkName(`${SITE}/menu/`), "Open affected page: /menu/");
});

test("one page renders the same way wherever a surface asks for it", () => {
  const link = evidenceLink("/locations/austin", SITE);
  assert.deepEqual(link, {
    href: `${SITE}/locations/austin`,
    label: "/locations/austin",
    path: "/locations/austin",
    title: `${SITE}/locations/austin`,
    linkName: "Open affected page: /locations/austin",
    isLinkable: true,
  });
});

test("the full URL is available for a tooltip even on the homepage", () => {
  const link = evidenceLink("/", SITE);
  assert.equal(link.label, "Homepage (/)");
  assert.equal(link.title, `${SITE}/`, "the tooltip must carry the full URL, not the label");
  assert.equal(link.isLinkable, true);
});

test("a page with no resolvable origin still reads, it just does not link", () => {
  const link = evidenceLink("/menu/", "");
  assert.equal(link.isLinkable, false);
  assert.equal(link.href, "");
  assert.equal(link.label, "/menu/", "the customer must still see which page is affected");
});


test("issue modal uses the shared evidence URL contract", () => {
  const source = fs.readFileSync(new URL("../../src/components/issues/IssueDetailModal.jsx", import.meta.url), "utf8");
  assert.equal(source.includes("evidenceLink(page, siteOrigin)"), true);
  assert.equal(source.includes('target="_blank"'), true);
  assert.equal(source.includes('rel="noopener noreferrer"'), true);
  assert.equal(source.includes("Copy URL"), true);
  assert.equal(source.includes("aria-label={link.linkName}"), true);
});

test("PDF export uses the shared evidence URL contract and real links", () => {
  const source = fs.readFileSync(new URL("../../src/lib/exportScanReport.js", import.meta.url), "utf8");
  assert.equal(source.includes("evidenceLink(page, siteOrigin)"), true);
  assert.equal(source.includes("textWithLink"), true);
  assert.equal(source.includes("item.affected_pages.forEach(page => line"), false);
});
