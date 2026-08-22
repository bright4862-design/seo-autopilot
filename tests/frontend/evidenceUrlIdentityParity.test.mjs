import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import {
  evidenceUrlKey,
  templateFamilyKey,
} from "../../base44/functions/persistDurableScanAuthority/evidenceUrlIdentity.js";

/**
 * The JavaScript half of the shared URL identity contract.
 *
 * Python decides a repair's partitions; this runtime re-verifies them. A
 * disagreement about which URLs are the same page means either a valid payload
 * is rejected, or an invalid one passes while describing different pages. So
 * both sides assert the same table, and neither side owns it.
 */

const TABLE = JSON.parse(
  readFileSync(new URL("../fixtures/evidence-url-identity.json", import.meta.url), "utf8"),
);

test("the shared table is substantial enough to be worth trusting", () => {
  assert.ok(TABLE.cases.length >= 12);
});

test("JavaScript matches the shared table exactly", () => {
  const drift = [];
  for (const row of TABLE.cases) {
    const family = templateFamilyKey(row.url);
    const evidence = evidenceUrlKey(row.url);
    if (family !== row.template_family_key) {
      drift.push(`${row.url}: family ${family} !== ${row.template_family_key}`);
    }
    if (evidence !== row.evidence_url_key) {
      drift.push(`${row.url}: evidence ${evidence} !== ${row.evidence_url_key}`);
    }
  }
  assert.deepEqual(drift, [], `the two runtimes disagree about URL identity:\n${drift.join("\n")}`);
});

// The properties are asserted here too, so a regression names the rule it broke
// rather than only pointing at a table row.

test("query order is not identity", () => {
  assert.equal(evidenceUrlKey("/a?b=1&c=2"), evidenceUrlKey("/a?c=2&b=1"));
});

test("a real parameter is identity", () => {
  assert.notEqual(evidenceUrlKey("/a?page=2"), evidenceUrlKey("/a"));
});

test("tracking parameters are not identity", () => {
  assert.equal(evidenceUrlKey("/a?utm_source=x&utm_medium=y"), evidenceUrlKey("/a"));
  assert.equal(evidenceUrlKey("/a?gclid=123"), evidenceUrlKey("/a"));
});

test("both duplicate keys survive", () => {
  assert.equal(evidenceUrlKey("/a?x=1&x=2"), evidenceUrlKey("/a?x=2&x=1"));
  assert.notEqual(evidenceUrlKey("/a?x=1&x=2"), evidenceUrlKey("/a?x=1"));
});

test("fragments, trailing slashes and case are not identity", () => {
  assert.equal(evidenceUrlKey("/a#top"), evidenceUrlKey("/a"));
  assert.equal(evidenceUrlKey("/a/"), evidenceUrlKey("/a"));
  assert.equal(evidenceUrlKey("/Doc.PDF"), evidenceUrlKey("/doc.pdf"));
});

test("template family identity ignores the query entirely", () => {
  assert.equal(templateFamilyKey("/a?page=2"), templateFamilyKey("/a"));
  assert.equal(templateFamilyKey("/a?utm_source=x"), templateFamilyKey("/a"));
});
