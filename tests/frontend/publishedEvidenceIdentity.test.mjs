import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import * as identity from "../../base44/functions/persistDurableScanAuthorityV7/evidenceUrlIdentity.js";

const table = JSON.parse(readFileSync(
  new URL("../fixtures/published-evidence-url-identity.json", import.meta.url), "utf8",
));

for (const row of table.cases) {
  test(`published evidence identity: ${row.name}`, () => {
    assert.equal(typeof identity.publishedEvidenceUrlKey, "function", "published identity export is missing");
    assert.equal(identity.publishedEvidenceUrlKey(row.url, {
      scanOrigin: row.scan_origin || "",
    }), row.expected);
  });
}

test("historical case and slash folding remains unchanged", () => {
  assert.deepEqual(["/x", "/x/", "/X"].map(identity.evidenceUrlKey), ["/x", "/x", "/x"]);
});
