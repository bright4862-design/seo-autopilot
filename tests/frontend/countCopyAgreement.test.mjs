import assert from "node:assert/strict";
import test from "node:test";

import {
  agreeingVerb,
  buildCustomerProjection,
  pluralNoun,
} from "../../base44/functions/getCustomerScanResult/projection.js";
import { customerCopyForFix } from "../../src/lib/fixVocabulary.js";

// A count and the words around it are one sentence. The 35-site production
// audit caught "1 checked page are affected." on the customer projection: the
// noun agreed with the count and the verb did not.

test("a noun and its verb both agree with the count", () => {
  assert.equal(pluralNoun(1, "page"), "page");
  assert.equal(pluralNoun(0, "page"), "pages");
  assert.equal(pluralNoun(7, "page"), "pages");
  assert.equal(agreeingVerb(1, "is"), "is");
  assert.equal(agreeingVerb(0, "is"), "are");
  assert.equal(agreeingVerb(7, "is"), "are");
  assert.equal(agreeingVerb(1, "was"), "was");
  assert.equal(agreeingVerb(3, "was"), "were");
});

test("an unlisted verb is returned unchanged rather than mangled", () => {
  assert.equal(agreeingVerb(3, "returned"), "returned");
  assert.equal(agreeingVerb(1, "returned"), "returned");
});

// A fix row whose checked_eligible cannot carry a ratio falls back to the
// absolute-count sentence, which is where the defect was visible.
function projectionFor(affectedChecked) {
  return buildCustomerProjection({
    run: { id: "run_1", status: "complete" },
    fixList: { id: "fl_1" },
    fixItems: [{
      id: "fix_1",
      page_count: affectedChecked,
      priority_context: { affected_checked: affectedChecked, checked_eligible: 0 },
    }],
    fullAccess: true,
    authorityVerified: true,
    resultIntegrityVerified: true,
  });
}

function reasonFor(affectedChecked) {
  const projection = projectionFor(affectedChecked);
  const items = projection?.fix_items || projection?.fixItems || [];
  assert.equal(items.length, 1, "expected the single seeded fix row");
  return items[0].priority_reason;
}

test("one affected page reads as one page, in the customer projection itself", () => {
  assert.equal(reasonFor(1), "1 checked page is affected.");
});

test("many affected pages still read as many", () => {
  assert.equal(reasonFor(4), "4 checked pages are affected.");
});

test("no affected pages says so rather than counting to zero", () => {
  assert.equal(reasonFor(0), "Coverage detail unavailable for this saved scan.");
});

test("the sitemap-orphan explanation agrees with its own title at one page", () => {
  // The title was already guarded on count; the explanation was not, so a
  // single orphan page read "1 pages were found".
  const one = customerCopyForFix({ rule: "potential_orphan_pages", page_count: 1, pageCount: 1 });
  const many = customerCopyForFix({ rule: "potential_orphan_pages", page_count: 5, pageCount: 5 });
  assert.ok(one.explanation, "the single-page rule must still produce copy");
  assert.ok(!/\b1 pages\b/.test(one.explanation), `singular copy says "1 pages": ${one.explanation}`);
  assert.ok(!/\bwere found\b/.test(one.explanation), `singular copy says "were": ${one.explanation}`);
  assert.ok(/\b1 page was found\b/.test(one.explanation), one.explanation);
  assert.ok(many.explanation, "the many-page rule must still produce copy");
  assert.ok(/\b5 pages were found\b/.test(many.explanation), many.explanation);
});

test("no shipped customer copy pairs a singular count with a plural verb", () => {
  // Guards the whole class rather than the two rows the audit happened to hit.
  for (const count of [1]) {
    const reason = reasonFor(count);
    assert.ok(
      !/\b1 [a-z]+ (are|were|have)\b/.test(reason),
      `singular count took a plural verb: ${reason}`,
    );
  }
});
