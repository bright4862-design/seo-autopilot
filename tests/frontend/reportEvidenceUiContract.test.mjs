import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  customerRedirectEvidenceRows,
  customerRepairObservationRows,
} from "../../src/lib/repairCardModel.js";

const card = {
  evidence: {
    redirectEvidence: [
      {
        requested_url: "https://example.com/old",
        redirect_chain: [{ url: "https://example.com/old", status: 301, location: "https://example.com/" }],
        final_url: "https://example.com/",
        final_status: 200,
        fetch_error: null,
        classification: "redirect_to_wrong_destination",
      },
      {
        requested_url: "https://example.com/slow",
        redirect_chain: [],
        final_url: "https://example.com/final",
        final_status: 0,
        fetch_error: "timed out",
        classification: "redirect_destination_unverified",
      },
    ],
    repairObservationCount: 25,
    repairObservationSamples: [
      { page_url: "/products/a", status: 200, issue_type: "canonical_missing", canonical_url: "" },
      { page_url: "/products/b", status: 200, issue_type: "missing_meta_description", meta_description: "", meta_description_state: "missing" },
    ],
  },
};

test("redirect customer evidence states destination truth and verification without guessing a replacement", () => {
  const rows = customerRedirectEvidenceRows(card, "https://example.com");
  assert.equal(rows[0].classificationLabel, "Wrong destination");
  assert.equal(rows[0].verificationLabel, "Verified response");
  assert.equal(rows[0].statusLabel, "HTTP 200");
  assert.equal(rows[0].requested.href, "https://example.com/old");
  assert.equal(rows[0].destination.href, "https://example.com/");
  assert.ok(!("replacement" in rows[0]));

  assert.equal(rows[1].classificationLabel, "Could not verify destination");
  assert.equal(rows[1].verificationLabel, "Needs verification");
  assert.equal(rows[1].statusLabel, "No verified final status");
});

test("repair observation rows preserve explicit missing values", () => {
  const rows = customerRepairObservationRows(card, "https://example.com");
  assert.equal(rows.length, 2);
  assert.equal(rows[0].page.href, "https://example.com/products/a");
  assert.equal(rows[0].valueLabel, "Canonical observed: missing");
  assert.equal(rows[1].valueLabel, "Meta description observed: missing");
  assert.equal(rows[0].statusLabel, "HTTP 200");
});

test("FixList renders persisted observations, redirect truth, and raw integer scan coverage", () => {
  const source = fs.readFileSync(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
  assert.match(source, /customerRedirectEvidenceRows/);
  assert.match(source, /customerRepairObservationRows/);
  assert.match(source, /scanCoverageDisclosure/);
  assert.match(source, /Observed redirect evidence/);
  assert.match(source, /Observed page evidence/);
  assert.match(source, /What this scan actually reached/);
  assert.match(source, /URLs attempted/);
  assert.doesNotMatch(source, /usable_html_page_count.*urls_attempted/);
});
