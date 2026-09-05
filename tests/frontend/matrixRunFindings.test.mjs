import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { customerCopyForFix } from "../../src/lib/fixVocabulary.js";
import { evidenceLink } from "../../src/lib/evidenceUrl.js";

/**
 * A 30-site matrix run surfaced two customer-facing faults on the live page.
 *
 * The affected-URL list was plain text, so an owner working through twelve
 * pages had to retype every one of them; and the copy still named SEO
 * machinery -- "canonical URLs" in a headline, "conversion pages" as a label
 * for something an owner calls a contact form.
 */

const page = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");

function customerCard(start, end) {
  const from = page.indexOf(start);
  return page.slice(from, page.indexOf(end, from));
}

test("every affected URL is clickable, not just the representative one", () => {
  // The card showed one linked "Representative" page per group and then a plain
  // <li> for each of the rest. The list under "All affected URLs" is the one an
  // owner actually works from.
  const list = customerCard('All affected URLs', "No affected URL list was persisted");
  assert.ok(list.length > 0, "the affected-URL list must exist");

  assert.match(list, /evidenceLink\(page, websiteUrl\)/, "each row resolves through the shared link contract");
  assert.match(list, /pageLink\.isLinkable \?/, "a row links only when the contract says it is safe");
  assert.match(list, /href=\{pageLink\.href\}/);
  assert.match(list, /rel="noopener noreferrer"/, "an external link must not hand the opener over");
  assert.match(list, /aria-label=\{pageLink\.linkName\}/);
  assert.doesNotMatch(
    list,
    /<li key=\{page\} className="break-all">\{page\}<\/li>/,
    "a raw page string rendered as text is what this test exists to prevent",
  );
});

test("an unlinkable page still renders, as text rather than a dead link", () => {
  // resolveEvidenceUrl returns "" for a relative path with no trustworthy
  // origin, and for an unsafe scheme. Dropping those rows would silently
  // shorten a list whose count is stated directly above it.
  const list = customerCard('All affected URLs', "No affected URL list was persisted");
  assert.match(list, /<span title=\{pageLink\.title\}>\{pageLink\.label\}<\/span>/);

  assert.equal(evidenceLink("/pricing", "").isLinkable, false);
  assert.equal(evidenceLink("javascript:alert(1)", "https://example.com").isLinkable, false);
  assert.equal(evidenceLink("/pricing", "https://example.com").isLinkable, true);
});

test("the loudest line on a card never names SEO machinery", () => {
  // "Canonical URL" is the correct technical term and it belongs on the Check
  // line, where someone briefing a developer looks. In the headline it is the
  // one line a non-technical owner reads -- and this card's own body already
  // explained the fix as a "preferred-page setting" without it.
  const copy = customerCopyForFix({ rule: "canonical_missing", page_count: 12, affected_pages: Array(12).fill("/a") });

  assert.doesNotMatch(copy.title, /canonical/i, `jargon in the headline: ${copy.title}`);
  assert.match(copy.title, /which version/i);
  assert.equal(copy.technicalLabel, "Canonical URL", "the technical name is kept where it is useful");
});

test("no customer headline carries a term an owner would have to look up", () => {
  const jargon = /\b(canonical|noindex|robots\.txt|crawl budget|indexab\w*|meta robots|hreflang|schema markup|conversion page)/i;
  const rules = [
    "canonical_missing", "canonical_target_noindex", "missing_meta_description",
    "missing_h1", "image_alt_text", "duplicate_title", "redirect_chain",
    "sitemap_redirect", "internal_link_redirect", "potential_orphan_pages",
    "redirect_destination_noindex", "broken_location_template_content",
  ];
  for (const rule of rules) {
    for (const family of ["", "conversion", "standard", "location_landing", "guide_article"]) {
      const copy = customerCopyForFix({ rule, page_count: 6, affected_pages: Array(6).fill("/a"), page_template_family: family });
      assert.doesNotMatch(copy.title, jargon, `${rule}/${family || "no family"}: ${copy.title}`);
    }
  }
});

test("page groups are named by what they do, not by the classifier's key", () => {
  // "conversion pages" is marketing vocabulary and "standard pages" names the
  // classifier's default bucket. Neither is a thing an owner calls a page.
  const conversion = customerCopyForFix({
    rule: "missing_h1", page_count: 8, affected_pages: Array(8).fill("/a"), page_template_family: "conversion",
  });
  assert.match(conversion.title, /sign-up and contact pages/);
  assert.doesNotMatch(conversion.title, /conversion/i);

  const standard = customerCopyForFix({
    rule: "image_alt_text", page_count: 7, affected_pages: Array(7).fill("/a"), page_template_family: "standard",
  });
  assert.doesNotMatch(standard.title, /standard pages/i, `internal bucket name leaked: ${standard.title}`);

  // A family that already reads plainly must not be churned.
  const location = customerCopyForFix({
    rule: "missing_h1", page_count: 5, affected_pages: Array(5).fill("/a"), page_template_family: "location_landing",
  });
  assert.match(location.title, /location pages/);
});

test("the section headings match the vocabulary on the cards beneath them", () => {
  const presentation = fs.readFileSync(new URL("../../src/lib/repairPresentation.js", import.meta.url), "utf8");
  assert.doesNotMatch(presentation, /conversion: "Conversion pages"/);
  assert.match(presentation, /conversion: "Sign-up and contact pages"/);
  assert.doesNotMatch(presentation, /route_boundary: "Website routes"/, '"routes" is developer vocabulary');
});
